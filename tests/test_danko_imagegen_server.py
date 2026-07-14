import importlib.util
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVER = (
    ROOT
    / "skills"
    / "third-party-imagegen"
    / "mcp_server"
    / "danko_imagegen_server.py"
)


def load_module():
    module_directory = str(SERVER.parent)
    sys.path.insert(0, module_directory)
    try:
        spec = importlib.util.spec_from_file_location("danko_imagegen_server", SERVER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(module_directory)


class FakeDankoImageError(RuntimeError):
    pass


class FakeImageRequest:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def _fake_core(
        self,
        *,
        route_error: Exception | None = None,
        generate_error: Exception | None = None,
        edit_error: Exception | None = None,
    ):
        route = SimpleNamespace(
            api_key="route-secret",
            base_url="https://dankotoken.com/v1/",
            source="danko",
            host="dankotoken.com",
        )
        result = SimpleNamespace(
            content=b"fake-png-bytes",
            output_path=Path("generated.png"),
            source="danko",
            host="dankotoken.com",
            model="gpt-image-2",
            output_format="png",
        )

        def resolve_danko_route(*args, **kwargs):
            if route_error is not None:
                raise route_error
            return route

        def generate_image(*args, **kwargs):
            if generate_error is not None:
                raise generate_error
            return result

        def edit_image(*args, **kwargs):
            if edit_error is not None:
                raise edit_error
            return result

        return SimpleNamespace(
            DankoImageError=FakeDankoImageError,
            ImageRequest=FakeImageRequest,
            resolve_danko_route=resolve_danko_route,
            generate_image=generate_image,
            edit_image=edit_image,
        )

    def test_direct_stdio_import_resolves_sibling_script_helpers(self) -> None:
        scripts = SERVER.parents[1] / "scripts"

        self.assertEqual(
            (scripts / "codex_route.py").resolve(),
            Path(sys.modules["codex_route"].__file__).resolve(),
        )
        self.assertEqual(
            (scripts / "generate_image.py").resolve(),
            Path(sys.modules["generate_image"].__file__).resolve(),
        )

    def test_generate_tool_returns_image_and_sanitized_text(self) -> None:
        content = self.mod.generate_danko_image("red dog", core=self._fake_core())

        self.assertEqual("image", content[0].type)
        self.assertNotIn("secret", content[1].text)
        self.assertIn("saved_path", content[1].text)
        self.assertNotIn("red dog", content[1].text)

    def test_edit_tool_rejects_non_local_input_path(self) -> None:
        with self.assertRaises(self.mod.ToolError):
            self.mod.edit_danko_image(
                "change fur",
                "https://example.com/dog.png",
                core=self._fake_core(),
            )

    def test_route_errors_are_actionable_and_secret_free(self) -> None:
        fake_core = self._fake_core(
            route_error=FakeDankoImageError("provider response: route-secret")
        )

        with self.assertRaises(self.mod.ToolError) as raised:
            self.mod.generate_danko_image("red dog", core=fake_core)

        self.assertIn("route", str(raised.exception).lower())
        self.assertNotIn("route-secret", str(raised.exception))

    def test_generate_provider_error_is_secret_free(self) -> None:
        fake_core = self._fake_core(
            generate_error=FakeDankoImageError(
                "provider response: token=provider-secret prompt=red dog"
            )
        )

        with self.assertRaises(self.mod.ToolError) as raised:
            self.mod.generate_danko_image("red dog", core=fake_core)

        self.assertNotIn("provider-secret", str(raised.exception))
        self.assertNotIn("red dog", str(raised.exception))

    def test_edit_provider_error_is_secret_free(self) -> None:
        fake_core = self._fake_core(
            edit_error=FakeDankoImageError(
                "provider response: token=provider-secret prompt=change fur"
            )
        )

        with self.assertRaises(self.mod.ToolError) as raised:
            self.mod.edit_danko_image("change fur", "source.png", core=fake_core)

        self.assertNotIn("provider-secret", str(raised.exception))
        self.assertNotIn("change fur", str(raised.exception))

    def test_instructions_prefer_danko_without_disabling_builtin_imagegen(self) -> None:
        instructions = self.mod.mcp.instructions.lower()

        self.assertIn("intended replacement path for built-in image_gen", instructions)
        self.assertNotIn("built-in image_gen is disabled", instructions)

    def test_stdio_runner_uses_mcp_stdio_transport(self) -> None:
        original_run = self.mod.mcp.run
        calls = []
        self.mod.mcp.run = lambda **kwargs: calls.append(kwargs)
        try:
            self.mod.run_stdio()
        finally:
            self.mod.mcp.run = original_run

        self.assertEqual([{"transport": "stdio"}], calls)

    def test_registered_tools_are_exactly_the_danko_pair(self) -> None:
        module = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
        registered = set()
        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if not (
                    isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp"
                    and decorator.func.attr == "tool"
                ):
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                        registered.add(keyword.value.value)

        self.assertEqual({"generate_danko_image", "edit_danko_image"}, registered)


if __name__ == "__main__":
    unittest.main()
