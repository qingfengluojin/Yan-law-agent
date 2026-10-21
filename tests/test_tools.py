from __future__ import annotations

import unittest
from pathlib import Path

from lawagent.retriever import Retriever
from lawagent.tools import ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(FIXTURE)
        cls.tools = ToolRegistry(cls.retriever)

    def test_search_returns_articles_and_ids(self) -> None:
        result = self.tools.execute("search_statutes", {"query": "经济补偿"})
        self.assertTrue(result.ok)
        self.assertTrue(result.top_ids)
        self.assertIn("articles", result.data)

    def test_search_no_results_returns_actionable_hint(self) -> None:
        result = self.tools.execute("search_statutes", {"query": "zzzzzz"})
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "no_results")
        self.assertTrue(result.hint)

    def test_search_rejects_invalid_top_k(self) -> None:
        result = self.tools.execute("search_statutes", {"query": "经济补偿", "top_k": 99})
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid_args")

    def test_get_article_resolves_short_law_name(self) -> None:
        result = self.tools.execute("get_article", {"law": "测试劳动法", "article_no": "2"})
        self.assertTrue(result.ok)
        self.assertEqual(result.top_ids, ["测试劳动法#2"])

    def test_get_article_not_found_has_hint(self) -> None:
        result = self.tools.execute("get_article", {"law": "测试劳动法", "article_no": "999"})
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "article_not_found")
        self.assertIn("测试劳动法", result.hint)

    def test_verify_citation_rejects_mismatch(self) -> None:
        result = self.tools.execute(
            "verify_citation",
            {
                "law": "测试劳动法",
                "article_no": "1",
                "quote": "不存在的引用文本。",
            },
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "quote_not_found")

    def test_unknown_tool_is_rejected(self) -> None:
        result = self.tools.execute("delete_everything", {})
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "unknown_tool")


if __name__ == "__main__":
    unittest.main()
