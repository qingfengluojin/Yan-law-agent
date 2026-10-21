import unittest
from pathlib import Path

from lawagent.agent import AgentRunner
from lawagent.llm import MockProvider
from lawagent.retriever import Retriever

DATA = Path(__file__).parents[1] / "data/articles.jsonl"


class MockProviderSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(DATA)

    def _run(self, question: str):
        return AgentRunner(self.retriever, MockProvider()).run(question)

    def test_social_insurance_question_selects_article_38(self) -> None:
        result = self._run("公司不交社保，解除劳动合同能要补偿吗？")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "38")

        article = self.retriever.get_article(
            result.answer.citations[0].law,
            result.answer.citations[0].article_no,
        )
        self.assertIsNotNone(article)
        self.assertEqual(result.answer.citations[0].quote, article.text)

    def test_trial_period_wage_question_selects_article_20(self) -> None:
        result = self._run("试用期工资最低是多少？")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "20")

    def test_economic_compensation_standard_selects_article_47(self) -> None:
        result = self._run("经济补偿按什么标准计算？")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "47")

    def test_economic_compensation_monthly_wage_selects_article_27(self) -> None:
        result = self._run("经济补偿的月工资怎么计算？")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "27")

    def test_chinese_article_number_selects_article_38(self) -> None:
        result = self._run("劳动合同法第三十八条原文")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "38")

    def test_trial_period_wage_short_query_selects_article_20(self) -> None:
        result = self._run("试用期工资")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "20")

    def test_work_injury_non_participation_selects_article_62(self) -> None:
        result = self._run("工伤认定后，单位未参加工伤保险怎么办？")
        self.assertEqual(result.answer.status, "ok")
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "62")


if __name__ == "__main__":
    unittest.main()
