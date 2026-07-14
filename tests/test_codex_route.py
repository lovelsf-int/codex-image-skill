import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


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
