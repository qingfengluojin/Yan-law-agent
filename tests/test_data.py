from collections import Counter
from pathlib import Path
import unittest

from lawagent.retriever import load_articles

DATA = Path(__file__).parents[1] / "data/articles.jsonl"

TOPICS = {
    "劳动合同解除": 8,
    "经济补偿": 8,
    "未缴社保": 8,
    "加班费": 8,
    "工伤/试用期": 8,
}


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.articles = load_articles(DATA)

    def test_size_and_unique_ids(self) -> None:
        self.assertEqual(len(self.articles), 40)
        self.assertEqual(
            len({article.article_id for article in self.articles}),
            40,
        )

    def test_topic_and_law_type_distribution(self) -> None:
        topics = Counter(article.topic for article in self.articles)
        self.assertEqual(topics, Counter(TOPICS))

        law_types = Counter(article.law_type for article in self.articles)
        self.assertEqual(law_types, Counter({"法律": 34, "行政法规": 6}))

    def test_provenance_fields(self) -> None:
        self.assertTrue(
            all(article.source_url.startswith("http") for article in self.articles)
        )
        self.assertTrue(
            all(article.status == "current" for article in self.articles)
        )
        self.assertTrue(
            all(
                article.verified_at.isoformat() == "2026-10-20"
                for article in self.articles
            )
        )


if __name__ == "__main__":
    unittest.main()