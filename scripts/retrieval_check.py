import json
from pathlib import Path

from lawagent.retriever import Retriever, load_articles

DATA = Path("data/articles.jsonl")
DEV = Path("cases/retrieval_dev.jsonl")
TOP_K = 5


def main() -> None:
    retriever = Retriever(load_articles(DATA))
    known_ids = {article.article_id for article in retriever.articles}

    with DEV.open("r", encoding="utf-8") as handle:
        cases = [json.loads(line) for line in handle if line.strip()]

    top1_hits = 0
    case_hits = 0
    matched_articles = 0
    total_expected = 0

    for case in cases:
        expected = case["expected_article_ids"]
        unknown = [article_id for article_id in expected if article_id not in known_ids]
        if unknown:
            raise SystemExit(f"{case['id']}: unknown article ids: {unknown}")

        results = retriever.search(case["question"], top_k=TOP_K)
        top_ids = [article.article_id for article in results]
        missing = sorted(set(expected) - set(top_ids))

        top1_hit = bool(top_ids) and top_ids[0] in expected
        case_hit = not missing

        top1_hits += int(top1_hit)
        case_hits += int(case_hit)
        matched_articles += len(set(expected) & set(top_ids))
        total_expected += len(expected)

        print(f"[{case['id']}] {case['question']}")
        print(f"  top{TOP_K}: {top_ids}")
        print(f"  expected: {expected}")
        print(f"  missing: {missing}")
        print(f"  top1_hit: {top1_hit}")
        print(f"  case_hit: {case_hit}")
        print()

    print(f"top1_hit: {top1_hits}/{len(cases)}")
    print(f"case_hit: {case_hits}/{len(cases)}")
    print(f"article_recall: {matched_articles}/{total_expected}")


if __name__ == "__main__":
    main()