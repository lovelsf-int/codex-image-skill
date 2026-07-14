import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "skills" / "third-party-imagegen" / "scripts" / "codex_route.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("third_party_codex_route", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_codex_files(home: Path, config: str, auth: dict | None = None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(config, encoding="utf-8")
    if auth is not None:
        (home / "auth.json").write_text(json.dumps(auth), encoding="utf-8")


class CodexProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_standard_provider_uses_active_base_url_and_env_key(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                """
model_provider = "dankotoken"
[model_providers.dankotoken]
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
""",
            )
            route = self.mod.resolve_codex_route(
                home, {"DANKOTOKEN_API_KEY": "secret"}, dry_run=False
            )
            self.assertEqual(route.base_url, "https://dankotoken.com/v1/")
            self.assertEqual(route.api_key, "secret")
            self.assertEqual(route.provider_id, "dankotoken")
            self.assertEqual(route.credential_source, "provider.env_key")

    def test_non_active_provider_is_never_used(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                """
model_provider = "active"
[model_providers.active]
name = "Missing URL"
[model_providers.stale]
base_url = "https://stale.example/v1"
experimental_bearer_token = "stale-secret"
""",
            )
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=False)

    def test_cli_codex_home_wins_over_environment(self) -> None:
        route_home = Path("cli-home")
        self.assertEqual(
            self.mod.resolve_codex_home(str(route_home), {"CODEX_HOME": "env-home"}),
            route_home,
        )

    def test_environment_codex_home_wins_over_default(self) -> None:
        original_default = self.mod.DEFAULT_CODEX_HOME
        self.mod.DEFAULT_CODEX_HOME = Path("default-home")
        try:
            self.assertEqual(
                self.mod.resolve_codex_home(None, {"CODEX_HOME": "env-home"}),
                Path("env-home"),
            )
        finally:
            self.mod.DEFAULT_CODEX_HOME = original_default

    def test_openai_base_url_is_used_without_active_provider(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(home, 'openai_base_url = "https://openai.example/v1"')
            route = self.mod.resolve_codex_route(home, {}, dry_run=True)
            self.assertEqual(route.base_url, "https://openai.example/v1/")
            self.assertIsNone(route.provider_id)

    def test_openai_base_url_is_used_for_openai_provider(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "openai"
openai_base_url = "https://openai.example/v1"
''',
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=True)
            self.assertEqual(route.base_url, "https://openai.example/v1/")
            self.assertEqual(route.provider_id, "openai")

    def test_custom_provider_does_not_use_openai_base_url(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
openai_base_url = "https://openai.example/v1"
[model_providers.custom]
name = "Custom"
''',
            )
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_malformed_toml_is_invalid_not_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(home, "model_provider = [")
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_invalid_utf8_toml_is_invalid_not_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            home.mkdir(parents=True)
            (home / "config.toml").write_bytes(b"\xff")
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_dry_run_allows_missing_credential_with_valid_url(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://custom.example/v1"
env_key = "CUSTOM_API_KEY"
''',
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=True)
            self.assertEqual(route.api_key, "")
            self.assertEqual(route.credential_source, "none")

    def test_dry_run_still_requires_a_valid_url(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "not a url"
''',
            )
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_cc_switch_enhanced_mode_prefers_provider_token(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
experimental_bearer_token = "provider-secret"
requires_openai_auth = true
''',
                {"tokens": {"access_token": "oauth-secret"}},
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=False)
            self.assertEqual(route.api_key, "provider-secret")
            self.assertEqual(
                route.credential_source, "provider.experimental_bearer_token"
            )
            self.assertNotIn("oauth-secret", repr(route))

    def test_cc_switch_legacy_mode_reads_only_auth_json_api_key(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
''',
                {
                    "OPENAI_API_KEY": "legacy-secret",
                    "tokens": {"access_token": "oauth-secret"},
                },
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=False)
            self.assertEqual(route.api_key, "legacy-secret")
            self.assertEqual(route.credential_source, "auth.json.OPENAI_API_KEY")

    def test_proxy_managed_requires_loopback(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "http://127.0.0.1:15721/v1"
experimental_bearer_token = "PROXY_MANAGED"
''',
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=False)
            self.assertEqual(route.base_url, "http://127.0.0.1:15721/v1/")

            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
experimental_bearer_token = "PROXY_MANAGED"
''',
            )
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=False)
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_proxy_managed_rejects_non_allowlisted_loopback_address(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "http://127.0.0.2:15721/v1"
experimental_bearer_token = "PROXY_MANAGED"
''',
            )
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=False)
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_codex_route(home, {}, dry_run=True)

    def test_oauth_only_auth_json_is_not_an_api_key(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
''',
                {"tokens": {"access_token": "oauth-secret"}},
            )
            with self.assertRaises(self.mod.RouteUnavailable):
                self.mod.resolve_codex_route(home, {}, dry_run=False)

    def test_provider_auth_command_uses_injected_runner(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
[model_providers.custom.auth]
command = "credential-helper"
args = ["--token"]
timeout_ms = 1000
''',
            )
            runner = Mock(return_value="command-secret")
            route = self.mod.resolve_codex_route(
                home, {}, dry_run=False, auth_command_runner=runner
            )
            self.assertEqual(route.api_key, "command-secret")
            self.assertEqual(route.credential_source, "provider.auth.command")
            runner.assert_called_once_with(
                {
                    "command": "credential-helper",
                    "args": ["--token"],
                    "timeout_ms": 1000,
                }
            )

    def test_provider_token_does_not_run_auth_command(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
experimental_bearer_token = "provider-secret"
[model_providers.custom.auth]
command = "credential-helper"
''',
            )
            runner = Mock()
            route = self.mod.resolve_codex_route(
                home, {}, dry_run=False, auth_command_runner=runner
            )
            self.assertEqual(route.api_key, "provider-secret")
            runner.assert_not_called()

    def test_provider_env_key_does_not_run_auth_command(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
env_key = "CUSTOM_API_KEY"
[model_providers.custom.auth]
command = "credential-helper"
''',
            )
            runner = Mock()
            route = self.mod.resolve_codex_route(
                home,
                {"CUSTOM_API_KEY": "environment-secret"},
                dry_run=False,
                auth_command_runner=runner,
            )
            self.assertEqual(route.api_key, "environment-secret")
            self.assertEqual(route.credential_source, "provider.env_key")
            runner.assert_not_called()

    def test_top_level_token_precedes_legacy_auth_json_key(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(
                home,
                '''
model_provider = "custom"
experimental_bearer_token = "top-level-secret"
[model_providers.custom]
base_url = "https://relay.example/v1"
''',
                {"OPENAI_API_KEY": "legacy-secret"},
            )
            route = self.mod.resolve_codex_route(home, {}, dry_run=False)
            self.assertEqual(route.api_key, "top-level-secret")
            self.assertEqual(route.credential_source, "experimental_bearer_token")

    def test_malformed_ipv6_url_is_invalid(self) -> None:
        with self.assertRaises(self.mod.RouteInvalid):
            self.mod.validate_base_url("https://[::1")


class AuthCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def assert_auth_failure_is_sanitized(self, error: BaseException) -> None:
        command = "sentinel-command"
        secret = "sentinel-secret"
        with patch.object(self.mod.subprocess, "run", side_effect=error):
            with self.assertRaises(self.mod.RouteInvalid) as caught:
                self.mod.run_auth_command(
                    {"command": command, "args": [secret]}
                )
        exception = caught.exception
        formatted = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        self.assertIsNone(exception.__cause__)
        self.assertIsNone(exception.__context__)
        for sentinel in (command, secret):
            self.assertNotIn(sentinel, formatted)
            self.assertNotIn(sentinel, repr(exception.__cause__))
            self.assertNotIn(sentinel, repr(exception.__context__))

    def test_run_auth_command_returns_trimmed_stdout(self) -> None:
        completed = Mock(returncode=0, stdout=" command-secret\n")
        with patch.object(self.mod.subprocess, "run", return_value=completed) as run:
            token = self.mod.run_auth_command(
                {
                    "command": "credential-helper",
                    "args": ["--token"],
                    "timeout_ms": 1000,
                }
            )
        self.assertEqual(token, "command-secret")
        run.assert_called_once()

    def test_run_auth_command_timeout_hides_exception_context(self) -> None:
        self.assert_auth_failure_is_sanitized(
            subprocess.TimeoutExpired(
                ["sentinel-command", "sentinel-secret"],
                1,
                output="sentinel-secret",
            )
        )

    def test_run_auth_command_os_error_hides_exception_context(self) -> None:
        self.assert_auth_failure_is_sanitized(
            OSError("sentinel-command failed with sentinel-secret")
        )

    def test_run_auth_command_rejects_nonzero_exit(self) -> None:
        completed = Mock(returncode=1, stdout="unused")
        with patch.object(self.mod.subprocess, "run", return_value=completed):
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.run_auth_command({"command": "credential-helper"})

    def test_run_auth_command_rejects_empty_stdout(self) -> None:
        completed = Mock(returncode=0, stdout="  \n")
        with patch.object(self.mod.subprocess, "run", return_value=completed):
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.run_auth_command({"command": "credential-helper"})


class EnvironmentRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_auto_uses_environment_only_when_codex_is_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            route = self.mod.resolve_route(
                "auto",
                codex_home=Path(directory),
                env={
                    "OPENAI_BASE_URL": "https://environment.example/v1",
                    "OPENAI_API_KEY": "environment-key",
                },
                dry_run=False,
            )
            self.assertEqual(route.source, "env")
            self.assertEqual(route.base_url, "https://environment.example/v1/")
            self.assertEqual(route.api_key, "environment-key")

    def test_auto_does_not_hide_invalid_codex_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_files(home, "model_provider = [")
            with self.assertRaises(self.mod.RouteInvalid):
                self.mod.resolve_route(
                    "auto",
                    codex_home=home,
                    env={
                        "OPENAI_BASE_URL": "https://environment.example/v1",
                        "OPENAI_API_KEY": "environment-key",
                    },
                    dry_run=False,
                )


if __name__ == "__main__":
    unittest.main()
