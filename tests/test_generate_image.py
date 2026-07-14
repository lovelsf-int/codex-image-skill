import base64
import importlib.util
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "third-party-imagegen" / "scripts" / "generate_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("third_party_generate_image", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_missing_base_url_fails_even_for_dry_run(self) -> None:
        with self.assertRaisesRegex(self.mod.ConfigError, "OPENAI_BASE_URL is required"):
            self.mod.load_config({}, dry_run=True)

    def test_missing_key_fails_for_live_call(self) -> None:
        with self.assertRaisesRegex(self.mod.ConfigError, "OPENAI_API_KEY is required"):
            self.mod.load_config(
                {"OPENAI_BASE_URL": "https://token.example/v1"}, dry_run=False
            )

    def test_dry_run_allows_missing_key_but_keeps_custom_host(self) -> None:
        config = self.mod.load_config(
            {"OPENAI_BASE_URL": "https://token.example/v1"}, dry_run=True
        )
        self.assertEqual(config.base_url, "https://token.example/v1/")
        self.assertEqual(config.host, "token.example")
        self.assertEqual(config.api_key, "")

    def test_invalid_base_urls_are_rejected(self) -> None:
        invalid_urls = (
            "token.example/v1",
            "ftp://token.example/v1",
            "https://user:pass@token.example/v1",
            "https://token.example/v1?secret=value",
        )
        for value in invalid_urls:
            with self.subTest(value=value):
                with self.assertRaises(self.mod.ConfigError):
                    self.mod.validate_base_url(value)

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

    def test_dry_run_summary_contains_no_key(self) -> None:
        args = self.mod.parse_args(["--prompt", "A small dog", "--dry-run"])
        config = self.mod.load_config(
            {
                "OPENAI_BASE_URL": "https://token.example/v1",
                "OPENAI_API_KEY": "test-api-key",
            },
            dry_run=True,
        )
        summary = self.mod.sanitized_summary(
            config, self.mod.build_payload(args), Path(args.out)
        )
        self.assertIn("token.example", summary)
        self.assertNotIn("test-api-key", summary)


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_custom_base_url_is_passed_to_client_and_image_is_written(self) -> None:
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

        def factory(config):
            captured["config"] = config
            return Client()

        with TemporaryDirectory() as directory:
            out = Path(directory) / "dog.png"
            args = self.mod.parse_args(["--prompt", "A small dog", "--out", str(out)])
            stream = io.StringIO()
            result = self.mod.run(
                args,
                env={
                    "OPENAI_API_KEY": "test-api-key",
                    "OPENAI_BASE_URL": "https://token.example/v1",
                },
                client_factory=factory,
                stdout=stream,
            )
            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), raw)
            self.assertEqual(captured["config"].base_url, "https://token.example/v1/")
            self.assertEqual(captured["payload"]["model"], "gpt-image-2")
            self.assertNotIn("test-api-key", stream.getvalue())

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
        args = self.mod.parse_args(["--prompt", "A small dog", "--dry-run"])

        def forbidden_factory(config):
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


if __name__ == "__main__":
    unittest.main()
