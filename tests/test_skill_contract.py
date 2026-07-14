import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
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


class SkillContractTests(unittest.TestCase):
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
            'short_description: "Generate GPT images through the active Codex route"',
            metadata,
        )
        self.assertIn("$third-party-imagegen", metadata)

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
            "## 默认行为：跟随 Codex",
            "## Codex Home 选择",
            "## 标准 Codex 提供商示例",
            "## CC Switch 兼容性",
            "## 显式环境变量回退",
            "## 命令行示例",
            "## 安全与输出契约",
            "## 提供商兼容性",
            "## 测试与兼容矩阵",
        ):
            with self.subTest(language="zh-CN", heading=heading):
                self.assertIn(heading, chinese)
        for heading in (
            "# Codex API ImageGen Skill",
            "## Scope",
            "## Requirements",
            "## Installation",
            "## Default Behavior: Follow Codex",
            "## Codex Home Selection",
            "## Standard Codex Provider Example",
            "## CC Switch Compatibility",
            "## Explicit Environment Fallback",
            "## CLI Examples",
            "## Security and Output Contract",
            "## Provider Compatibility",
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
