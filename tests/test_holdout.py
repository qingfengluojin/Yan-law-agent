from __future__ import annotations

import json
import unittest
from pathlib import Path

from lawagent.retriever import load_articles

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/articles.jsonl"
EVAL = ROOT / "cases/cases.jsonl"
DEV = ROOT / "cases/retrieval_dev.jsonl"
HOLDOUT = ROOT / "cases/holdout.jsonl"


def load_questions(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        return {json.loads(line)["question"] for line in handle if line.strip()}


class HoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.known_ids = {article.article_id for article in load_articles(DATA)}
        with HOLDOUT.open("r", encoding="utf-8") as handle:
            cls.cases = [json.loads(line) for line in handle if line.strip()]

    def test_holdout_schema_and_gold_ids(self) -> None:
        self.assertEqual(len(self.cases), 10)
        self.assertEqual(len({case["id"] for case in self.cases}), 10)
        for case in self.cases:
            self.assertTrue(case["question"].strip())
            self.assertIn(case["type"], {"single_hop", "multi_hop", "no_answer"})
            for article_id in case["gold_article_ids"]:
                self.assertIn(article_id, self.known_ids)
            if case["type"] == "no_answer":
                self.assertEqual(case["gold_article_ids"], [])

    def test_holdout_questions_do_not_overlap_development_sets(self) -> None:
        holdout = {case["question"] for case in self.cases}
        self.assertFalse(holdout & load_questions(EVAL))
        self.assertFalse(holdout & load_questions(DEV))


if __name__ == "__main__":
    unittest.main()
