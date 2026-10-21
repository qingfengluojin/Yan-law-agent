from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lawagent.retriever import Retriever, extract_article_no, load_articles

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class RetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(FIXTURE)

    def test_legal_synonym_search_finds_social_insurance_article(self) -> None:
        results = self.retriever.search("用人单位未缴社保", top_k=5)
        self.assertTrue(results)
        self.assertEqual(results[0].article_id, "测试劳动法#1")

    def test_article_number_route_puts_exact_match_first(self) -> None:
        results = self.retriever.search("测试劳动法第3条", top_k=2)
        self.assertTrue(results)
        self.assertEqual(results[0].article_id, "测试劳动法#3")

    def test_get_article_accepts_short_law_name_and_bare_number(self) -> None:
        article = self.retriever.get_article("测试劳动法", "第3条")
        self.assertIsNotNone(article)
        self.assertEqual(article.article_no, "3")

    def test_unknown_article_returns_none(self) -> None:
        self.assertIsNone(self.retriever.get_article("测试劳动法", "999"))

    def test_empty_file_loads_as_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            self.assertEqual(load_articles(path), [])

    def test_chinese_article_number_route(self) -> None:
        self.assertEqual(extract_article_no("测试劳动法第三条"), "3")
        self.assertIsNotNone(self.retriever.get_article("测试劳动法", "第三条"))

        results = self.retriever.search("测试劳动法第三条", top_k=2)
        self.assertTrue(results)
        self.assertEqual(results[0].article_id, "测试劳动法#3")


if __name__ == "__main__":
    unittest.main()
