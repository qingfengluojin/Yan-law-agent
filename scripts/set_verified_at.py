import argparse
import csv
from datetime import date
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, help="主题名称")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument(
        "--path",
        default="data/articles.working.csv",
        help="工作 CSV 路径",
    )
    args = parser.parse_args()

    try:
        date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("日期必须是 YYYY-MM-DD 格式") from exc

    path = Path(args.path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0].keys()) if rows else []

    updated = 0
    for row in rows:
        if row["topic"] != args.topic:
            continue
        if not row["text"].strip() or not row["source_url"].strip():
            continue
        row["verified_at"] = args.date
        updated += 1

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"updated {updated} rows with verified_at={args.date}")


if __name__ == "__main__":
    main()