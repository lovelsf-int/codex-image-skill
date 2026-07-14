import base64
import importlib.util
import json
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
    sys.path.insert(0, module_directory)
    try:
        spec = importlib.util.spec_from_file_location("danko_imagegen_core", CORE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
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

    def test_danko_route_allows_active_provider_auth_command(self) -> None:
        home = Path("danko-codex")
        auth = {"command": "danko-token-command"}
        config = {
            "model_provider": "dankotoken",
            "model_providers": {
                "dankotoken": {
                    "base_url": "https://dankotoken.com/v1/",
                    "auth": auth,
                }
            },
        }

        with patch.object(
            self.mod,
            "load_toml",
            return_value=config,
        ), patch.object(
            self.mod,
            "run_auth_command",
            return_value="command-api-key",
        ) as command_runner:
            route = self.mod.resolve_danko_route({}, home)

        self.assertEqual("command-api-key", route.api_key)
        self.assertEqual("provider.auth.command", route.credential_source)
        command_runner.assert_called_once_with(auth)

    def test_danko_route_allows_legacy_auth_json_api_key(self) -> None:
        config = {
            "model_provider": "dankotoken",
            "model_providers": {
                "dankotoken": {"base_url": "https://dankotoken.com/v1/"}
            },
        }

        with TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "auth.json").write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "legacy-api-key",
                        "tokens": {"access_token": "must-not-be-used"},
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                self.mod,
                "load_toml",
                return_value=config,
            ):
                route = self.mod.resolve_danko_route({}, home)

        self.assertEqual("legacy-api-key", route.api_key)
        self.assertEqual("auth.json.OPENAI_API_KEY", route.credential_source)

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

    def test_generate_rejects_empty_prompt_before_constructing_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.mod.ImageRequest(prompt=" "),
                    self.route,
                    client_factory,
                    Path(directory),
                )

        client_factory.assert_not_called()

    def test_generate_rejects_invalid_model_before_constructing_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.mod.ImageRequest(prompt="A small dog", model="other-model"),
                    self.route,
                    client_factory,
                    Path(directory),
                )

        client_factory.assert_not_called()

    def test_generate_rejects_unsupported_quality_before_constructing_client(
        self,
    ) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.mod.ImageRequest(
                        prompt="A small dog", quality="ultra"
                    ),
                    self.route,
                    client_factory,
                    Path(directory),
                )

        client_factory.assert_not_called()

    def test_generate_rejects_unsupported_format_before_constructing_client(
        self,
    ) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.mod.ImageRequest(
                        prompt="A small dog", output_format="gif"
                    ),
                    self.route,
                    client_factory,
                    Path(directory),
                )

        client_factory.assert_not_called()

    def test_generate_rejects_malformed_size_before_constructing_client(
        self,
    ) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.mod.ImageRequest(
                        prompt="A small dog", size="1024-by-1024"
                    ),
                    self.route,
                    client_factory,
                    Path(directory),
                )

        client_factory.assert_not_called()

    def test_generate_rejects_output_outside_workspace_before_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.request,
                    self.route,
                    client_factory,
                    workspace,
                    root / "outside.png",
                )

        client_factory.assert_not_called()

    def test_default_output_uses_danko_directory_and_requested_format(self) -> None:
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
        )
        fake_client = MagicMock()
        fake_client.images.generate.return_value = response
        request = self.mod.ImageRequest(
            prompt="A small dog", output_format="webp"
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            result = self.mod.generate_image(
                request, self.route, lambda route: fake_client, workspace
            )

            expected = workspace / "output" / "danko-imagegen" / "generated.webp"
            self.assertEqual(expected.resolve(), result.output_path)
            self.assertEqual(PNG_BYTES, expected.read_bytes())

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

    def test_edit_rejects_empty_prompt_before_constructing_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_png = workspace / "source.png"
            source_png.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.mod.ImageRequest(prompt=" "),
                    source_png,
                    self.route,
                    client_factory,
                    workspace,
                )

        client_factory.assert_not_called()

    def test_edit_rejects_invalid_model_before_constructing_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_png = workspace / "source.png"
            source_png.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.mod.ImageRequest(prompt="A small dog", model="other-model"),
                    source_png,
                    self.route,
                    client_factory,
                    workspace,
                )

        client_factory.assert_not_called()

    def test_edit_rejects_path_outside_workspace_before_constructing_client(
        self,
    ) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            source_png = root / "outside.png"
            source_png.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.request,
                    source_png,
                    self.route,
                    client_factory,
                    workspace,
                )

        client_factory.assert_not_called()

    def test_edit_rejects_unsupported_extension_before_constructing_client(
        self,
    ) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_gif = workspace / "source.gif"
            source_gif.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.request,
                    source_gif,
                    self.route,
                    client_factory,
                    workspace,
                )

        client_factory.assert_not_called()

    def test_edit_rejects_output_outside_workspace_before_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            source_png = workspace / "source.png"
            source_png.write_bytes(PNG_BYTES)
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.request,
                    source_png,
                    self.route,
                    client_factory,
                    workspace,
                    root / "outside.png",
                )

        client_factory.assert_not_called()

    def test_output_collision_is_rejected(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            output = workspace / "generated.png"
            output.write_bytes(b"existing")
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.generate_image(
                    self.request,
                    self.route,
                    client_factory,
                    workspace,
                    output,
                )

        client_factory.assert_not_called()

    def test_edit_rejects_existing_output_before_constructing_client(self) -> None:
        client_factory = MagicMock()

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_png = workspace / "source.png"
            source_png.write_bytes(PNG_BYTES)
            output = workspace / "edited.png"
            output.write_bytes(b"existing")
            with self.assertRaises(self.mod.DankoImageError):
                self.mod.edit_image(
                    self.request,
                    source_png,
                    self.route,
                    client_factory,
                    workspace,
                    output,
                )

        client_factory.assert_not_called()

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
