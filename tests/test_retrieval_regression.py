import json
from pathlib import Path
import unittest

from lawagent.retriever import Retriever

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/articles.jsonl"
DEV = ROOT / "cases/retrieval_dev.jsonl"


class RetrievalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(DATA)
        with DEV.open("r", encoding="utf-8") as handle:
            cls.cases = [json.loads(line) for line in handle if line.strip()]

    def test_dev_set_top5_recall(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                top_ids = {
                    article.article_id
                    for article in self.retriever.search(
                        case["question"],
                        top_k=5,
                    )
                }
                expected = set(case["expected_article_ids"])
                self.assertTrue(expected <= top_ids)