import base64
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
CORE = (
    ROOT
    / "skills"
    / "third-party-imagegen"
    / "mcp_server"
    / "danko_imagegen_core.py"
)

PNG_BYTES = b"fake-png-bytes"


def load_module():
    module_directory = str(CORE.parent)
    scripts_directory = str(CORE.parents[1] / "scripts")
    sys.path.insert(0, module_directory)
    sys.path.insert(0, scripts_directory)
    try:
        spec = importlib.util.spec_from_file_location("danko_imagegen_core", CORE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_directory)
        sys.path.remove(module_directory)


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_dedicated_danko_key_uses_default_base_url(self) -> None:
        route = self.mod.resolve_danko_route(
            {"DANKOTOKEN_API_KEY": "dedicated-secret"}, Path("codex")
        )
        self.assertEqual("https://dankotoken.com/v1/", route.base_url)
        self.assertEqual("dankotoken.com", route.host)
        self.assertEqual("danko", route.source)

    def test_dedicated_danko_key_ignores_generic_openai_environment(self) -> None:
        route = self.mod.resolve_danko_route(
            {
                "DANKOTOKEN_API_KEY": "dedicated-secret",
                "OPENAI_API_KEY": "wrong-secret",
                "OPENAI_BASE_URL": "https://wrong.example/v1",
            },
            Path("codex"),
        )
        self.assertEqual("dedicated-secret", route.api_key)
        self.assertEqual("https://dankotoken.com/v1/", route.base_url)

    def test_codex_fallback_accepts_only_dankotoken_host(self) -> None:
        danko_home = Path("danko-codex")
        non_danko_home = Path("other-codex")
        config = {"model_provider": "dankotoken"}
        provider = {"env_key": "DANKOTOKEN_API_KEY"}

        with patch.object(
            self.mod,
            "load_toml",
            return_value=config,
        ), patch.object(
            self.mod,
            "active_provider",
            return_value=("dankotoken", provider),
        ), patch.object(
            self.mod,
            "resolve_codex_base_url",
            side_effect=[
                "https://dankotoken.com/v1/",
                "https://other.example/v1/",
            ],
        ), patch.object(
            self.mod,
            "provider_credential",
            return_value=("codex-secret", "provider.env_key"),
        ) as credential:
            self.assertEqual(
                "codex", self.mod.resolve_danko_route({}, danko_home).source
            )
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.resolve_danko_route({}, non_danko_home)
        credential.assert_called_once()

    def test_codex_fallback_accepts_www_dankotoken_host(self) -> None:
        home = Path("danko-codex")
        config = {"model_provider": "dankotoken"}
        provider = {"env_key": "DANKOTOKEN_API_KEY"}

        with patch.object(
            self.mod,
            "load_toml",
            return_value=config,
        ), patch.object(
            self.mod,
            "active_provider",
            return_value=("dankotoken", provider),
        ), patch.object(
            self.mod,
            "resolve_codex_base_url",
            return_value="https://www.dankotoken.com/v1/",
        ), patch.object(
            self.mod,
            "provider_credential",
            return_value=("codex-secret", "provider.env_key"),
        ):
            route = self.mod.resolve_danko_route({}, home)

        self.assertEqual("www.dankotoken.com", route.host)
        self.assertEqual("codex", route.source)

    def test_non_danko_route_never_resolves_auth_command_or_auth_json(self) -> None:
        config = {
            "model_provider": "other",
            "model_providers": {
                "other": {
                    "base_url": "https://other.example/v1/",
                    "auth": {"command": "must-not-run"},
                }
            },
        }

        with patch.object(
            self.mod,
            "load_toml",
            return_value=config,
        ), patch.object(
            self.mod,
            "provider_credential",
            side_effect=AssertionError("credential resolution must not run"),
        ) as credential:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.resolve_danko_route({}, Path("non-danko-codex"))
        credential.assert_not_called()

    def test_codex_route_errors_are_secret_free(self) -> None:
        with patch.object(
            self.mod,
            "load_toml",
            side_effect=self.mod.RouteError("route failed: secret-value"),
        ):
            with self.assertRaises(self.mod.DankoImageError) as raised:
                self.mod.resolve_danko_route({}, Path("codex"))
        self.assertNotIn("secret-value", str(raised.exception))


class ImageOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def setUp(self) -> None:
        self.request = self.mod.ImageRequest(prompt="A small dog")
        self.route = self.mod.ResolvedRoute(
            api_key="route-secret",
            base_url="https://dankotoken.com/v1/",
            host="dankotoken.com",
            source="danko",
            provider_id="dankotoken",
            credential_source="DANKOTOKEN_API_KEY",
            codex_home=None,
        )

    def test_generate_writes_and_returns_base64_image(self) -> None:
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
        )
        fake_client = MagicMock()
        fake_client.images.generate.return_value = response

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            output = workspace / "generated.png"
            result = self.mod.generate_image(
                self.request, self.route, lambda route: fake_client, workspace, output
            )

            self.assertEqual(PNG_BYTES, result.content)
            self.assertEqual(output.resolve(), result.output_path)
            self.assertEqual(PNG_BYTES, output.read_bytes())
            fake_client.images.generate.assert_called_once_with(
                **self.request.to_payload()
            )

    def test_edit_passes_local_image_to_images_edit(self) -> None:
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
        )
        fake_client = MagicMock()
        fake_client.images.edit.return_value = response

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_png = workspace / "source.png"
            source_png.write_bytes(PNG_BYTES)
            result = self.mod.edit_image(
                self.request,
                source_png,
                self.route,
                lambda route: fake_client,
                workspace,
                workspace / "edited.png",
            )

            self.assertEqual(PNG_BYTES, result.content)
            fake_client.images.edit.assert_called_once()
            self.assertEqual(
                self.request.to_payload(),
                {
                    key: value
                    for key, value in fake_client.images.edit.call_args.kwargs.items()
                    if key != "image"
                },
            )

    def test_edit_rejects_path_outside_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.validate_input_image(Path("C:/outside.png"), workspace)

    def test_edit_rejects_unsupported_input_extension(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_gif = workspace / "source.gif"
            source_gif.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.validate_input_image(source_gif, workspace)

    def test_output_collision_is_rejected(self) -> None:
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
        )
        fake_client = MagicMock()
        fake_client.images.generate.return_value = response

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            output = workspace / "generated.png"
            output.write_bytes(b"existing")
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.request,
                    self.route,
                    lambda route: fake_client,
                    workspace,
                    output,
                )

    def test_url_only_response_is_rejected(self) -> None:
        fake_client = MagicMock()
        fake_client.images.generate.return_value = SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="https://example.invalid/image.png")]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.request,
                    self.route,
                    lambda route: fake_client,
                    workspace,
                    workspace / "generated.png",
                )


if __name__ == "__main__":
    unittest.main()
