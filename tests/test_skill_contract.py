from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "third-party-imagegen"


class SkillContractTests(unittest.TestCase):
    def test_skill_metadata_and_routing_contract(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: third-party-imagegen", skill)
        self.assertIn("description: Use when", skill)
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
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "test.yml").is_file())


if __name__ == "__main__":
    unittest.main()
