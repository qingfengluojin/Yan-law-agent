from __future__ import annotations

import unittest
from pathlib import Path

from lawagent.retriever import Retriever
from lawagent.schema import Citation
from lawagent.verify import CitationVerifier
from scripts.evaluate import _citation_metrics

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class EvaluateMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(FIXTURE)
        cls.verifier = CitationVerifier(cls.retriever)

    def test_raw_metrics_keep_duplicates_and_invalid_citations(self) -> None:
        citation = Citation(
            law="测试劳动法",
            article_no="1",
            quote="用人单位应当依法为劳动者缴纳社会保险费。",
        )
        metrics = _citation_metrics([citation, citation], self.verifier, set())
        self.assertEqual(metrics["count"], 2)
        self.assertEqual(metrics["unique"], 1)
        self.assertEqual(metrics["duplicates"], 1)
        self.assertEqual(metrics["existence"], 2)
        self.assertEqual(metrics["verbatim"], 2)
        self.assertEqual(metrics["unsupported"], 2)


if __name__ == "__main__":
    unittest.main()
