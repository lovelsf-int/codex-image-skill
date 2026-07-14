import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "third-party-imagegen"
GENERATE_IMAGE = SKILL_DIR / "scripts" / "generate_image.py"
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
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
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
            "OAuth token",
            "database",
            "api.openai.com",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "gpt-image-2",
            "data[].b64_json",
        ):
            with self.subTest(term=term):
                self.assertIn(term, readme)
        for document_name, document in (("README", readme), ("SKILL", skill)):
            with self.subTest(document=document_name):
                self.assertIn(SANITIZED_SUMMARY_CONTRACT, document)
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "test.yml").is_file())

    def test_english_readme_matches_public_routing_contract(self) -> None:
        self.assertTrue(README_EN.is_file())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english = README_EN.read_text(encoding="utf-8")
        self.assertIn("[English](README.en.md)", readme)
        self.assertIn("[简体中文](README.md)", english)
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
            with self.subTest(term=term):
                self.assertIn(term, english)
        self.assertIn(SANITIZED_SUMMARY_CONTRACT, english)


if __name__ == "__main__":
    unittest.main()
