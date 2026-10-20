from __future__ import annotations

import unittest
from pathlib import Path

from lawagent.retriever import Retriever
from lawagent.schema import Citation
from lawagent.verify import CitationVerifier

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(FIXTURE)
        cls.verifier = CitationVerifier(cls.retriever)

    def test_exact_quote_passes_and_source_is_filled(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位应当依法为劳动者缴纳社会保险费。",
        )
        result = self.verifier.verify(citation)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.citation)
        self.assertTrue(result.citation.source_url.startswith("https://example.invalid/"))

    def test_whitespace_difference_is_normalized(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位 应当依法 为劳动者缴纳社会保险费。",
        )
        self.assertTrue(self.verifier.verify(citation).ok)

    def test_ellipsis_is_rejected(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位……缴纳社会保险费。",
        )
        result = self.verifier.verify(citation)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "quote_contains_ellipsis")

    def test_wrong_quote_is_rejected(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位应当支付经济补偿。",
        )
        result = self.verifier.verify(citation)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "quote_not_found")

    def test_citation_not_from_this_run_is_rejected(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位应当依法为劳动者缴纳社会保险费。",
        )
        result = self.verifier.verify(
            citation,
            allowed_article_ids={"测试劳动法#2"},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "not_from_this_run")


if __name__ == "__main__":
    unittest.main()