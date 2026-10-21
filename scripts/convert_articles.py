import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

SRC = Path("data/articles.working.csv")
DST = Path("data/articles.jsonl")

FIELDS = [
    "law",
    "law_type",
    "article_no",
    "topic",
    "text",
    "source_url",
    "verified_at",
    "review_status",
    "reviewer",
    "status",
]

TOPICS = {
    "劳动合同解除",
    "经济补偿",
    "未缴社保",
    "加班费",
    "工伤/试用期",
}

LAW_TYPES = {"法律", "行政法规"}
PAGE_MARK = re.compile(r"[－—–-]\s*\d+\s*[－—–-]")


def normalize_iso_date(value: str) -> str:
    """Accept Excel-style separators but persist dates as YYYY-MM-DD."""

    return date.fromisoformat(value.strip().replace("/", "-")).isoformat()


def main() -> None:
    with SRC.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 40:
        raise SystemExit(f"expected 40 rows, got {len(rows)}")

    records = []
    article_ids = []

    for line_number, row in enumerate(rows, start=2):
        required_fields = [field for field in FIELDS if field != "reviewer"]
        missing = [field for field in required_fields if not (row.get(field) or "").strip()]
        if missing:
            raise SystemExit(f"line {line_number}: missing fields: {', '.join(missing)}")

        record = {field: (row.get(field) or "").strip() for field in FIELDS}
        if record["review_status"] not in {"self_checked", "independently_verified"}:
            raise SystemExit(f"line {line_number}: invalid review_status")
        if record["review_status"] == "independently_verified" and not record["reviewer"]:
            raise SystemExit(f"line {line_number}: reviewer is required after independent review")

        if record["topic"] not in TOPICS:
            raise SystemExit(f"line {line_number}: invalid topic: {record['topic']}")

        if record["law_type"] not in LAW_TYPES:
            raise SystemExit(f"line {line_number}: invalid law_type: {record['law_type']}")

        try:
            record["verified_at"] = normalize_iso_date(record["verified_at"])
        except ValueError as exc:
            raise SystemExit(f"line {line_number}: verified_at must be a valid date") from exc

        if "……" in record["text"] or "..." in record["text"]:
            raise SystemExit(f"line {line_number}: ellipsis is not allowed in text")

        if PAGE_MARK.search(record["text"]):
            raise SystemExit(f"line {line_number}: page marker found in text")

        article_id = f"{record['law']}#{record['article_no']}"
        article_ids.append(article_id)
        records.append(record)

    duplicates = [article_id for article_id, count in Counter(article_ids).items() if count > 1]
    if duplicates:
        raise SystemExit(f"duplicate article ids: {duplicates}")

    with DST.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"wrote {len(records)} articles to {DST}")


if __name__ == "__main__":
    main()
