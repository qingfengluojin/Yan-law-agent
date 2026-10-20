from __future__ import annotations

import unittest
from datetime import date

from lawagent.schema import Article, Citation


class SchemaTests(unittest.TestCase):
    def test_article_accepts_numeric_article_no(self) -> None:
        article = Article(
            law="测试劳动法",
            article_no=3,
            text="测试文本。",
            topic="测试",
            source_url="https://example.invalid/3",
            verified_at=date(2026, 10, 19),
        )
        self.assertEqual(article.article_no, "3")
        self.assertEqual(article.article_id, "测试劳动法#3")

    def test_article_rejects_unknown_status(self) -> None:
        with self.assertRaises(Exception):
            Article(
                law="测试劳动法",
                article_no="3",
                text="测试文本。",
                topic="测试",
                source_url="https://example.invalid/3",
                verified_at=date(2026, 10, 19),
                status="outdated",
            )

    def test_citation_requires_non_blank_quote(self) -> None:
        with self.assertRaises(Exception):
            Citation(law="测试劳动法", article_no="1", quote="   ")


if __name__ == "__main__":
    unittest.main()