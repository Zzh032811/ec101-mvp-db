import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    def test_skill_requires_one_output_folder_per_dealer(self):
        skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("outputs/<经销商名称>/", skill)
        self.assertIn("不同经销商的输出不得混放", skill)

    def test_skill_requires_complete_union_field_mapping(self):
        skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("经销商各模块原始字段全集 ∪ EC101 V1 标准字段全集", skill)
        self.assertIn("非V1字段", skill)

    def test_skill_routes_finance_cloud_to_its_platform_rules(self):
        skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("platform-rules/财经云.md", skill)
        self.assertIn("validate_caijingyun_case.py", skill)

    def test_skill_requires_task_card_and_input_quality_gate(self):
        skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("活动任务卡", skill)
        self.assertIn("Phase 0.5", skill)
        self.assertIn("输入数据质检规则.md", skill)
        self.assertIn("平台操作手册标准.md", skill)


if __name__ == "__main__":
    unittest.main()
