import json
import unittest
from collections import Counter
from pathlib import Path

from lawagent.retriever import load_articles

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/articles.jsonl"
CASES = ROOT / "cases/cases.jsonl"

ALLOWED_TYPES = {"single_hop", "multi_hop", "no_answer", "recovery"}
EXPECTED_DISTRIBUTION = Counter(
    {
        "single_hop": 8,
        "multi_hop": 6,
        "no_answer": 3,
        "recovery": 3,
    }
)


class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        articles = load_articles(DATA)
        cls.known_ids = {article.article_id for article in articles}

        with CASES.open("r", encoding="utf-8") as handle:
            cls.cases = [json.loads(line) for line in handle if line.strip()]

    def test_case_count_and_distribution(self) -> None:
        self.assertEqual(len(self.cases), 20)
        self.assertEqual(len({case["id"] for case in self.cases}), 20)
        self.assertEqual(
            Counter(case["type"] for case in self.cases),
            EXPECTED_DISTRIBUTION,
        )

    def test_gold_ids_and_required_fields(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["question"].strip())
                self.assertIn(case["type"], ALLOWED_TYPES)
                self.assertIsInstance(case["gold_article_ids"], list)

                for article_id in case["gold_article_ids"]:
                    self.assertIn(article_id, self.known_ids)

                if case["type"] == "single_hop":
                    self.assertGreaterEqual(len(case["gold_article_ids"]), 1)

                if case["type"] == "multi_hop":
                    self.assertGreaterEqual(len(case["gold_article_ids"]), 2)

                if case["type"] == "no_answer":
                    self.assertEqual(case["gold_article_ids"], [])

                if case["type"] == "recovery":
                    self.assertGreaterEqual(len(case["gold_article_ids"]), 1)


if __name__ == "__main__":
    unittest.main()
