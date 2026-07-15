import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
INSTALLER_CONFIG_WRITER = ROOT / "scripts" / "write_mcp_config.py"
INSTALLER_SH = ROOT / "scripts" / "install-danko-imagegen.sh"
INSTALLER_PS1 = ROOT / "scripts" / "install-danko-imagegen.ps1"
SKILL_DIR = ROOT / "skills" / "third-party-imagegen"
GENERATE_IMAGE = SKILL_DIR / "scripts" / "generate_image.py"
README_ZH = ROOT / "README.md"
README_EN = ROOT / "README.en.md"

SANITIZED_SUMMARY_FIELDS = {
    "source",
    "provider",
    "credential_source",
    "host",
    "model",
    "output",
    "output_format",
    "quality",
    "size",
}
SANITIZED_SUMMARY_CONTRACT = (
    "Sanitized summary fields are exactly and only: `source`, `provider`, "
    "`credential_source`, `host`, `model`, `output`, `output_format`, "
    "`quality`, and `size`. `key`, `prompt`, `config`, OAuth data, and "
    "token values are never included."
)
SANITIZED_SUMMARY_CONTRACT_ZH = (
    "脱敏摘要字段严格且仅限以下九项：`source`、`provider`、`credential_source`、"
    "`host`、`model`、`output`、`output_format`、`quality` 和 `size`。摘要绝不包含 "
    "`key`、`prompt`、`config`、OAuth 数据或任何 token 值。"
)
PROXY_ALLOWLIST_EN = (
    "The exact `PROXY_MANAGED` allowlist contains only `localhost`, "
    "`127.0.0.1`, and `::1`."
)
PROXY_ALLOWLIST_ZH = (
    "`PROXY_MANAGED` 的精确允许列表仅包含 `localhost`、`127.0.0.1` 和 `::1`。"
)
TOMLI_CONTRACT_EN = (
    "Only Python 3.10 needs the conditional `tomli` compatibility dependency "
    "(`python_version < '3.11'`); Python 3.11 and newer use the standard-library "
    "TOML parser."
)
TOMLI_CONTRACT_ZH = (
    "只有 Python 3.10 需要条件依赖 `tomli`（`python_version < '3.11'`）；"
    "Python 3.11 及更高版本使用标准库中的 TOML 解析器。"
)
ENV_ROUTE_CONTRACT_EN = (
    "Live environment routing requires both a valid URL and a key. With "
    "`--dry-run`, a valid URL is required but the key is not."
)
ENV_ROUTE_CONTRACT_ZH = (
    "实时环境变量路由必须同时提供有效 URL 和密钥。使用 `--dry-run` 时必须提供"
    "有效 URL，但不要求提供密钥。"
)
MCP_SECTION_EN = "## Danko MCP Image Tools (Recommended)"
MCP_SECTION_ZH = "## Danko MCP 图像工具（推荐）"
MCP_CONFIGURATION_END_EN = "### MCP Tool Examples"
MCP_CONFIGURATION_END_ZH = "### MCP 工具示例"
MCP_ENV_VARS_TOML = (
    'env_vars = ["DANKOTOKEN_API_KEY", "DANKOTOKEN_BASE_URL", '
    '"DANKOTOKEN_ALLOW_CODEX_FALLBACK"]'
)
MCP_DEFAULT_OUTPUT = "output/danko-imagegen/generated.<format>"
LEGACY_CLI_SECTION_EN = "## Legacy CLI: Active Codex Provider Text-to-Image"
LEGACY_CLI_SECTION_ZH = "## 旧版 CLI：跟随活动 Codex 提供商（仅文本生成图像）"
PLUGIN_INSTALLATION_SECTION_EN = "### Plugin installation (recommended)"
PLUGIN_INSTALLATION_SECTION_ZH = "### 插件安装（推荐）"
PLUGIN_INSTALLATION_END_EN = "### Manual/legacy Skill-copy compatibility"
PLUGIN_INSTALLATION_END_ZH = "### 手动/旧版 Skill 复制兼容性"
SKILL_COPY_COMPATIBILITY_SECTION_EN = "### Manual/legacy Skill-copy compatibility"
SKILL_COPY_COMPATIBILITY_SECTION_ZH = "### 手动/旧版 Skill 复制兼容性"
INSTALLATION_END_EN = "## Danko MCP Image Tools (Recommended)"
INSTALLATION_END_ZH = "## Danko MCP 图像工具（推荐）"
MANUAL_MCP_SECTION_EN = "### Compatibility/manual MCP TOML setup"
MANUAL_MCP_SECTION_ZH = "### 兼容性/手动 MCP TOML 配置"


def parse_yaml_frontmatter(document: str) -> dict[str, str]:
    lines = document.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must begin with YAML frontmatter")

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            return metadata
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()

    raise ValueError("SKILL.md YAML frontmatter is not closed")


def section_after(document: str, heading: str, next_heading: str | None = None) -> str:
    start = document.index(heading)
    if next_heading is None:
        return document[start:]
    end = document.index(next_heading, start)
    return document[start:end]


class SkillContractTests(unittest.TestCase):
    def test_root_plugin_and_installer_declarations_match_contract(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual("danko-imagegen", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual("lovelsf-int", manifest["author"]["name"])
        self.assertEqual(
            "https://github.com/lovelsf-int/codex-image-skill",
            manifest["homepage"],
        )
        self.assertEqual(
            "https://github.com/lovelsf-int/codex-image-skill",
            manifest["repository"],
        )
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertEqual("Danko ImageGen", manifest["interface"]["displayName"])
        self.assertEqual("Productivity", manifest["interface"]["category"])
        self.assertEqual(
            ["Interactive", "Write"], manifest["interface"]["capabilities"]
        )
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 2)

        self.assertTrue(INSTALLER_CONFIG_WRITER.is_file())
        self.assertTrue(INSTALLER_SH.is_file())
        self.assertTrue(INSTALLER_PS1.is_file())
        self.assertFalse((ROOT / ".mcp.json").exists())

    def test_config_writer_manages_only_its_own_danko_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = Path(temporary_directory) / "config.toml"
            command = [
                sys.executable,
                str(INSTALLER_CONFIG_WRITER),
                "--config",
                str(config),
                "--python",
                "/tmp/danko/.venv/bin/python",
                "--server",
                "/tmp/danko/server.py",
                "--cwd",
                "/tmp/danko",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            first_install = config.read_text(encoding="utf-8")
            self.assertIn("# BEGIN DANKO_IMAGEGEN MCP", first_install)
            self.assertIn('command = "/tmp/danko/.venv/bin/python"', first_install)
            self.assertIn(MCP_ENV_VARS_TOML, first_install)

            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(first_install, config.read_text(encoding="utf-8"))

            config.write_text(
                first_install + "[mcp_servers.danko_imagegen]\ncommand = \"python\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("outside the managed installer block", result.stderr)

    def test_bilingual_danko_mcp_sections_match_the_documentation_contract(self) -> None:
        chinese = README_ZH.read_text(encoding="utf-8")
        english = README_EN.read_text(encoding="utf-8")
        english_mcp_configuration = section_after(
            english, MCP_SECTION_EN, MCP_CONFIGURATION_END_EN
        )
        chinese_mcp_configuration = section_after(
            chinese, MCP_SECTION_ZH, MCP_CONFIGURATION_END_ZH
        )
        english_legacy = section_after(english, LEGACY_CLI_SECTION_EN)
        chinese_legacy = section_after(chinese, LEGACY_CLI_SECTION_ZH)

        for term in (
            "intended replacement path",
            "Danko-specific",
            "generate_danko_image",
            "edit_danko_image",
            "local image-to-image",
            "https://dankotoken.com/v1",
            "env_vars",
            "DANKOTOKEN_API_KEY",
            "DANKOTOKEN_BASE_URL",
            "DANKOTOKEN_ALLOW_CODEX_FALLBACK=1",
            "Restart Codex after persistent Windows environment-variable changes",
            "explicitly set `DANKOTOKEN_BASE_URL` or modify\n"
            "the source default endpoint",
            "does not technically disable, remove,\n"
            "or modify Codex's built-in tool",
            "never falls back to `api.openai.com`",
            "convenience-first fallback",
            "provider auth command",
            "legacy `auth.json.OPENAI_API_KEY`",
            "stale official API key",
            "OAuth fields are never read",
            MCP_DEFAULT_OUTPUT,
        ):
            with self.subTest(language="en", term=term):
                self.assertIn(term, english_mcp_configuration)

        for term in (
            "预期替代路径",
            "Danko 专用",
            "generate_danko_image",
            "edit_danko_image",
            "图生图",
            "https://dankotoken.com/v1",
            "env_vars",
            "DANKOTOKEN_API_KEY",
            "DANKOTOKEN_BASE_URL",
            "DANKOTOKEN_ALLOW_CODEX_FALLBACK=1",
            "修改持久 Windows 环境变量后必须重启 Codex",
            "必须显式设置 `DANKOTOKEN_BASE_URL`，或修改源码中的默认端点",
            "不会在技术上禁用、移除或修改 Codex 的内置工具",
            "也不会回退到 `api.openai.com`",
            "便利性优先回退",
            "提供商身份验证命令",
            "旧式 `auth.json.OPENAI_API_KEY`",
            "过期的官方 API 密钥",
            "永不读取 OAuth 字段",
            MCP_DEFAULT_OUTPUT,
        ):
            with self.subTest(language="zh-CN", term=term):
                self.assertIn(term, chinese_mcp_configuration)

        self.assertIn(MCP_ENV_VARS_TOML, english_mcp_configuration)
        self.assertIn(MCP_ENV_VARS_TOML, chinese_mcp_configuration)
        self.assertIn(MCP_CONFIGURATION_END_EN, english)
        self.assertIn(MCP_CONFIGURATION_END_ZH, chinese)
        self.assertNotIn(MCP_SECTION_ZH, english)
        self.assertNotIn(MCP_SECTION_EN, chinese)
        self.assertLess(
            english.index(MCP_SECTION_EN), english.index(LEGACY_CLI_SECTION_EN)
        )
        self.assertLess(
            chinese.index(MCP_SECTION_ZH), chinese.index(LEGACY_CLI_SECTION_ZH)
        )
        self.assertIn("legacy, text-to-image-only path", english)
        self.assertIn("仅文本生成图像的旧版路径", chinese)
        self.assertNotIn("Image editing, masks, batch generation", english)
        self.assertNotIn("本 Skill 不支持图片编辑", chinese)
        self.assertIn("`--source auto` first uses the active Codex route.", english_legacy)
        self.assertIn("`--source auto` 优先使用当前 Codex 路由。", chinese_legacy)

    def test_bilingual_readmes_document_plugin_first_installation(self) -> None:
        chinese = README_ZH.read_text(encoding="utf-8")
        english = README_EN.read_text(encoding="utf-8")

        for (
            language,
            document,
            plugin_section,
            plugin_end,
            skill_copy_section,
            installation_end,
            manual_mcp_section,
            installer_contract,
            external_key_configuration,
        ) in (
            (
                "en",
                english,
                PLUGIN_INSTALLATION_SECTION_EN,
                PLUGIN_INSTALLATION_END_EN,
                SKILL_COPY_COMPATIBILITY_SECTION_EN,
                INSTALLATION_END_EN,
                MANUAL_MCP_SECTION_EN,
                "detects a\nPython 3.10+ command",
                "Configure `DANKOTOKEN_API_KEY` outside this repository",
            ),
            (
                "zh-CN",
                chinese,
                PLUGIN_INSTALLATION_SECTION_ZH,
                PLUGIN_INSTALLATION_END_ZH,
                SKILL_COPY_COMPATIBILITY_SECTION_ZH,
                INSTALLATION_END_ZH,
                MANUAL_MCP_SECTION_ZH,
                "检测 Python 3.10+",
                "请在仓库外部配置 `DANKOTOKEN_API_KEY`",
            ),
        ):
            plugin_installation = section_after(document, plugin_section, plugin_end)
            skill_copy_compatibility = section_after(
                document, skill_copy_section, installation_end
            )
            manual_mcp_compatibility = section_after(
                document, manual_mcp_section, MCP_CONFIGURATION_END_EN
                if language == "en"
                else MCP_CONFIGURATION_END_ZH,
            )

            for term in (
                "danko-imagegen",
                ".codex-plugin/plugin.json",
                "install-danko-imagegen",
                "DANKOTOKEN_API_KEY",
                plugin_section,
                installer_contract,
                external_key_configuration,
            ):
                with self.subTest(language=language, term=term):
                    self.assertIn(term, plugin_installation)
            with self.subTest(language=language, requirement="plugin-first"):
                self.assertLess(document.index(plugin_section), document.index(skill_copy_section))
                self.assertLess(document.index(plugin_section), document.index(manual_mcp_section))
            with self.subTest(language=language, requirement="no-copy-in-plugin"):
                self.assertNotIn("Copy-Item -Recurse", plugin_installation)
                self.assertNotIn("cp -R ./skills/third-party-imagegen", plugin_installation)
            with self.subTest(language=language, requirement="copy-is-compatibility-only"):
                self.assertIn("Copy-Item -Recurse", skill_copy_compatibility)
                self.assertIn(
                    "cp -R ./skills/third-party-imagegen", skill_copy_compatibility
                )
            with self.subTest(language=language, requirement="manual-mcp-is-compatibility-only"):
                self.assertIn("manual MCP TOML" if language == "en" else "手动 MCP TOML", manual_mcp_compatibility)
                self.assertNotIn(
                    "[mcp_servers.danko_imagegen]",
                    document[: document.index(manual_mcp_section)],
                )

        self.assertIn(
            "manual MCP TOML\ncompatibility option only", english
        )
        self.assertIn("手动 MCP TOML\n兼容性选项", chinese)

    def test_skill_describes_danko_mcp_tools_and_security_policy(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("generate_danko_image", skill)
        self.assertIn("edit_danko_image", skill)
        self.assertIn("DANKOTOKEN_API_KEY", skill)
        self.assertIn("DANKOTOKEN_ALLOW_CODEX_FALLBACK=1", skill)
        self.assertIn("api.openai.com", skill)
        self.assertIn("convenience-first fallback", skill)
        self.assertIn("provider auth command", skill)
        self.assertIn("legacy `auth.json.OPENAI_API_KEY`", skill)
        self.assertIn("stale official API key", skill)
        self.assertIn("OAuth fields are never read", skill)
        self.assertIn(MCP_DEFAULT_OUTPUT, skill)

    def test_skill_metadata_and_routing_contract(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        metadata = parse_yaml_frontmatter(skill)
        self.assertEqual("third-party-imagegen", metadata.get("name"))
        self.assertTrue(metadata.get("description", "").startswith("Use when"))
        self.assertIn("gpt-image-2", skill)
        self.assertIn("Never use the built-in `image_gen` tool", skill)
        self.assertIn("scripts/generate_image.py", skill)
        for term in (
            "--source auto|codex|env",
            "CODEX_HOME",
            "--codex-home",
            "model_provider",
            "env_key",
            "experimental_bearer_token",
            "auth.json.OPENAI_API_KEY",
            "PROXY_MANAGED",
            "CC Switch",
            "/v1/images/generations",
            "DankoToken",
            "OAuth tokens",
            "CC Switch database",
            "api.openai.com",
        ):
            with self.subTest(term=term):
                self.assertIn(term, skill)

    def test_sanitized_summary_ast_matches_public_contract(self) -> None:
        source = GENERATE_IMAGE.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(GENERATE_IMAGE))
        function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "sanitized_summary"
        )
        returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
        self.assertEqual(1, len(returns))

        returned = returns[0].value
        self.assertIsInstance(returned, ast.Call)
        self.assertTrue(returned.args)
        summary_dict = returned.args[0]
        self.assertIsInstance(summary_dict, ast.Dict)
        self.assertTrue(
            all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in summary_dict.keys)
        )
        self.assertEqual(
            SANITIZED_SUMMARY_FIELDS,
            {key.value for key in summary_dict.keys},
        )

    def test_openai_yaml_matches_skill(self) -> None:
        metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Third-Party ImageGen"', metadata)
        self.assertIn(
            'short_description: "Generate and edit images through Danko MCP"',
            metadata,
        )
        self.assertIn("$third-party-imagegen", metadata)
        self.assertIn("Danko MCP", metadata)
        self.assertNotIn("active Codex provider", metadata)

    def test_distribution_documents_explain_codex_auto_routing(self) -> None:
        readme = README_ZH.read_text(encoding="utf-8")
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for term in (
            "--source auto|codex|env",
            "CODEX_HOME",
            "--codex-home",
            "model_provider",
            "env_key",
            "experimental_bearer_token",
            "auth.json.OPENAI_API_KEY",
            "PROXY_MANAGED",
            "CC Switch",
            "/v1/images/generations",
            "DankoToken",
            "api.openai.com",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "gpt-image-2",
            "data[].b64_json",
        ):
            with self.subTest(term=term):
                self.assertIn(term, readme)
        self.assertIn(SANITIZED_SUMMARY_CONTRACT_ZH, readme)
        self.assertIn(SANITIZED_SUMMARY_CONTRACT, skill)
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "test.yml").is_file())

    def test_bilingual_readmes_match_public_routing_contract(self) -> None:
        self.assertTrue(README_ZH.is_file())
        self.assertTrue(README_EN.is_file())
        chinese = README_ZH.read_text(encoding="utf-8")
        english = README_EN.read_text(encoding="utf-8")
        self.assertIn("[English](README.en.md)", chinese.splitlines()[:5])
        self.assertIn("[简体中文](README.md)", english.splitlines()[:5])

        self.assertGreaterEqual(
            sum("\u4e00" <= character <= "\u9fff" for character in chinese),
            500,
            "README.md must be a complete Simplified Chinese guide",
        )
        for heading in (
            "# Codex API 图片生成 Skill",
            "## 适用范围",
            "## 使用要求",
            "## 安装",
            LEGACY_CLI_SECTION_ZH,
            "### Codex Home 选择",
            "### 标准 Codex 提供商示例",
            "### CC Switch 兼容性",
            "### 显式环境变量回退",
            "### 命令行示例",
            "### 安全与输出契约",
            "### 提供商兼容性",
            "## 测试与兼容矩阵",
        ):
            with self.subTest(language="zh-CN", heading=heading):
                self.assertIn(heading, chinese)
        for heading in (
            "# Codex API ImageGen Skill",
            "## Scope",
            "## Requirements",
            "## Installation",
            LEGACY_CLI_SECTION_EN,
            "### Codex Home Selection",
            "### Standard Codex Provider Example",
            "### CC Switch Compatibility",
            "### Explicit Environment Fallback",
            "### CLI Examples",
            "### Security and Output Contract",
            "### Provider Compatibility",
            "## Testing and Compatibility Matrix",
        ):
            with self.subTest(language="en", heading=heading):
                self.assertIn(heading, english)

        for term in (
            "Python 3.10+",
            "Windows PowerShell",
            "macOS",
            "Linux",
            "--source auto|codex|env",
            "CODEX_HOME",
            "--codex-home",
            "model_provider",
            "env_key",
            "experimental_bearer_token",
            "auth.json.OPENAI_API_KEY",
            "PROXY_MANAGED",
            "localhost",
            "127.0.0.1",
            "::1",
            "CC Switch",
            "/v1/images/generations",
            "DankoToken has no hardcoded priority",
            "OAuth fields",
            "tokens",
            "access_token",
            "refresh_token",
            "CC Switch SQLite database",
            "api.openai.com",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "gpt-image-2",
            "data[].b64_json",
            "GitHub Actions",
        ):
            with self.subTest(language="en", term=term):
                self.assertIn(term, english)

        for term in (
            "Python 3.10+",
            "Windows PowerShell",
            "macOS",
            "Linux",
            "--source auto|codex|env",
            "CODEX_HOME",
            "--codex-home",
            "model_provider",
            "env_key",
            "experimental_bearer_token",
            "auth.json.OPENAI_API_KEY",
            "PROXY_MANAGED",
            "localhost",
            "127.0.0.1",
            "::1",
            "CC Switch",
            "/v1/images/generations",
            "DankoToken",
            "OAuth",
            "tokens",
            "access_token",
            "refresh_token",
            "CC Switch SQLite 数据库",
            "api.openai.com",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "gpt-image-2",
            "data[].b64_json",
            "GitHub Actions",
        ):
            with self.subTest(language="zh-CN", term=term):
                self.assertIn(term, chinese)

        self.assertIn("并不代表优先级规则", chinese)
        self.assertIn("DankoToken has no hardcoded priority", english)
        self.assertIn(PROXY_ALLOWLIST_ZH, chinese)
        self.assertIn(PROXY_ALLOWLIST_EN, english)
        self.assertNotIn("such as `localhost`", chinese)
        self.assertNotIn("such as `localhost`", english)
        self.assertIn(TOMLI_CONTRACT_ZH, chinese)
        self.assertIn(TOMLI_CONTRACT_EN, english)
        self.assertIn(ENV_ROUTE_CONTRACT_ZH, chinese)
        self.assertIn(ENV_ROUTE_CONTRACT_EN, english)
        self.assertIn(SANITIZED_SUMMARY_CONTRACT_ZH, chinese)
        self.assertIn(SANITIZED_SUMMARY_CONTRACT, english)


if __name__ == "__main__":
    unittest.main()
