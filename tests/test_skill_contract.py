from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "third-party-imagegen"


class SkillContractTests(unittest.TestCase):
    def test_skill_metadata_and_routing_contract(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: third-party-imagegen", skill)
        self.assertIn("description: Use when", skill)
        self.assertIn("OPENAI_BASE_URL", skill)
        self.assertIn("OPENAI_API_KEY", skill)
        self.assertIn("gpt-image-2", skill)
        self.assertIn("Never use the built-in `image_gen` tool", skill)
        self.assertIn("scripts/generate_image.py", skill)

    def test_openai_yaml_matches_skill(self) -> None:
        metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Third-Party ImageGen"', metadata)
        self.assertIn('short_description: "Generate GPT images through a custom API"', metadata)
        self.assertIn("$third-party-imagegen", metadata)

    def test_distribution_documents_explain_strict_routing(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY", readme)
        self.assertIn("OPENAI_BASE_URL", readme)
        self.assertIn("gpt-image-2", readme)
        self.assertIn("No fallback", readme)
        self.assertIn("/v1/images/generations", readme)
        self.assertIn("data[].b64_json", readme)
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "test.yml").is_file())


if __name__ == "__main__":
    unittest.main()
