import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "third-party-imagegen" / "scripts" / "generate_image.py"


def load_module():
    scripts_directory = str(SCRIPT.parent)
    sys.path.insert(0, scripts_directory)
    try:
        spec = importlib.util.spec_from_file_location(
            "third_party_generate_image", SCRIPT
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_directory)


class ArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_source_options_default_to_auto_and_accept_explicit_values(self) -> None:
        self.assertEqual(
            self.mod.parse_args(["--prompt", "A small dog"]).source, "auto"
        )
        self.assertEqual(
            self.mod.parse_args(["--prompt", "A small dog", "--source", "codex"]).source,
            "codex",
        )
        self.assertEqual(
            self.mod.parse_args(["--prompt", "A small dog", "--source", "env"]).source,
            "env",
        )

    def test_codex_home_option_parses(self) -> None:
        args = self.mod.parse_args(
            ["--prompt", "A small dog", "--codex-home", "custom-codex-home"]
        )
        self.assertEqual(args.codex_home, "custom-codex-home")

    def test_payload_defaults_and_model_validation(self) -> None:
        args = self.mod.parse_args(["--prompt", "A small dog"])
        self.assertEqual(
            self.mod.build_payload(args),
            {
                "model": "gpt-image-2",
                "prompt": "A small dog",
                "size": "1024x1024",
                "quality": "medium",
                "output_format": "png",
            },
        )
        args.model = "image-2"
        with self.assertRaisesRegex(self.mod.ConfigError, "must start with gpt-image-"):
            self.mod.build_payload(args)

    def test_sanitized_summary_includes_route_identity_without_key(self) -> None:
        args = self.mod.parse_args(["--prompt", "A small dog", "--dry-run"])
        route = self.mod.ResolvedRoute(
            api_key="test-api-key",
            base_url="https://token.example/v1/",
            host="token.example",
            source="codex",
            provider_id="dankotoken",
            credential_source="provider.env_key",
            codex_home=Path("custom-codex-home"),
        )
        summary = self.mod.sanitized_summary(
            route, self.mod.build_payload(args), Path(args.out)
        )
        values = json.loads(summary)
        self.assertEqual(
            set(values),
            {
                "source",
                "provider",
                "credential_source",
                "host",
                "model",
                "output",
                "output_format",
                "quality",
                "size",
            },
        )
        self.assertEqual(values["source"], "codex")
        self.assertEqual(values["provider"], "dankotoken")
        self.assertEqual(values["credential_source"], "provider.env_key")
        self.assertEqual(values["host"], "token.example")
        self.assertNotIn("test-api-key", summary)


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_resolved_route_is_passed_to_client_factory_and_image_is_written(self) -> None:
        raw = b"fake-png-bytes"
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(raw).decode("ascii"))]
        )
        captured = {}
        route = self.mod.ResolvedRoute(
            api_key="route-api-key",
            base_url="https://token.example/v1/",
            host="token.example",
            source="codex",
            provider_id="dankotoken",
            credential_source="provider.env_key",
            codex_home=Path("custom-codex-home"),
        )

        class Images:
            def generate(self, **payload):
                captured["payload"] = payload
                return response

        class Client:
            images = Images()

        def resolver(source, *, codex_home, env, dry_run):
            captured["source"] = source
            captured["codex_home"] = codex_home
            captured["env"] = env
            captured["dry_run"] = dry_run
            return route

        def factory(received_route):
            captured["route"] = received_route
            return Client()

        with TemporaryDirectory() as directory:
            out = Path(directory) / "dog.png"
            args = self.mod.parse_args(
                [
                    "--prompt",
                    "A small dog",
                    "--source",
                    "codex",
                    "--codex-home",
                    "custom-codex-home",
                    "--out",
                    str(out),
                ]
            )
            stream = io.StringIO()
            result = self.mod.run(
                args,
                env={"IGNORED": "value"},
                route_resolver=resolver,
                client_factory=factory,
                stdout=stream,
            )
            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), raw)
            self.assertEqual(captured["source"], "codex")
            self.assertEqual(captured["codex_home"], Path("custom-codex-home"))
            self.assertIs(captured["route"], route)
            self.assertEqual(captured["route"].api_key, "route-api-key")
            self.assertEqual(captured["route"].base_url, "https://token.example/v1/")
            self.assertEqual(captured["payload"]["model"], "gpt-image-2")
            self.assertNotIn("route-api-key", stream.getvalue())

    def test_env_source_still_generates_with_environment_route(self) -> None:
        raw = b"fake-png-bytes"
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(raw).decode("ascii"))]
        )
        captured = {}

        class Images:
            def generate(self, **payload):
                captured["payload"] = payload
                return response

        class Client:
            images = Images()

        def factory(route):
            captured["route"] = route
            return Client()

        with TemporaryDirectory() as directory:
            out = Path(directory) / "dog.png"
            args = self.mod.parse_args(
                ["--prompt", "A small dog", "--source", "env", "--out", str(out)]
            )
            result = self.mod.run(
                args,
                env={
                    "OPENAI_API_KEY": "environment-api-key",
                    "OPENAI_BASE_URL": "https://environment.example/v1",
                },
                client_factory=factory,
            )
            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), raw)
            self.assertEqual(captured["route"].source, "env")
            self.assertEqual(
                captured["route"].base_url, "https://environment.example/v1/"
            )

    def test_existing_output_requires_force(self) -> None:
        with TemporaryDirectory() as directory:
            out = Path(directory) / "existing.png"
            out.write_bytes(b"old")
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                self.mod.atomic_write(out, b"new", force=False)
            self.mod.atomic_write(out, b"new", force=True)
            self.assertEqual(out.read_bytes(), b"new")

    def test_url_only_response_is_rejected(self) -> None:
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="https://example.invalid/image.png")]
        )
        with self.assertRaisesRegex(self.mod.ResponseError, "b64_json"):
            self.mod.decode_first_image(response)

    def test_invalid_base64_response_is_rejected(self) -> None:
        response = SimpleNamespace(data=[SimpleNamespace(b64_json="not base64")])
        with self.assertRaisesRegex(self.mod.ResponseError, "invalid base64"):
            self.mod.decode_first_image(response)

    def test_dry_run_never_constructs_a_client(self) -> None:
        args = self.mod.parse_args(
            ["--prompt", "A small dog", "--source", "env", "--dry-run"]
        )

        def forbidden_factory(route):
            raise AssertionError("client must not be constructed")

        stream = io.StringIO()
        result = self.mod.run(
            args,
            env={"OPENAI_BASE_URL": "https://token.example/v1"},
            client_factory=forbidden_factory,
            stdout=stream,
        )
        self.assertIsNone(result)
        self.assertIn("token.example", stream.getvalue())

    def test_loopback_codex_route_404_reports_cc_switch_endpoint_guidance(self) -> None:
        class Http404Error(Exception):
            status_code = 404

        route = self.mod.ResolvedRoute(
            api_key="PROXY_MANAGED",
            base_url="http://127.0.0.1:15721/v1/",
            host="127.0.0.1",
            source="codex",
            provider_id="cc-switch",
            credential_source="provider.experimental_bearer_token",
            codex_home=Path("custom-codex-home"),
        )
        captured = {}

        class Images:
            def generate(self, **payload):
                raise Http404Error

        class Client:
            images = Images()

        def resolver(source, *, codex_home, env, dry_run):
            captured["source"] = source
            return route

        def factory(received_route):
            captured["route"] = received_route
            return Client()

        stderr = io.StringIO()
        with patch.object(sys, "stderr", stderr):
            status = self.mod.main(
                ["--prompt", "A small dog", "--source", "codex"],
                env={},
                route_resolver=resolver,
                client_factory=factory,
            )
        self.assertEqual(status, 1)
        self.assertEqual(captured["source"], "codex")
        self.assertIs(captured["route"], route)
        self.assertIn("CC Switch local route", stderr.getvalue())
        self.assertIn("/images/generations", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
