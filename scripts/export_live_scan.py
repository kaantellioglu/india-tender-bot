"""Publish only records added or changed by the latest scanner run."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import openpyxl


def read_register(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book["04 Tender Register"]
        return {str(row[0]): tuple(row) for row in sheet.iter_rows(min_row=4, max_col=22, values_only=True) if row[0] is not None}
    finally:
        book.close()


def source_link(value):
    value = str(value or "").strip()
    try:
        url = urlsplit(value)
        return value if url.scheme in ("http", "https") and url.hostname and not url.username else None
    except ValueError:
        return None


def public_snapshot(before, after, scanned_at):
    results = []
    for identifier, row in after.items():
        old = before.get(identifier)
        if row == old:
            continue
        source = source_link(row[19])
        if not source or not (row[3] or row[4]):
            continue
        results.append({
            "id": identifier,
            "change": "updated" if old else "new",
            "buyer": row[1],
            "reference": row[3],
            "date": row[4],
            "status": row[5],
            "equipment": row[6],
            "description": row[7],
            "source": source,
        })
    return {"scanned_at": scanned_at, "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = public_snapshot(read_register(args.before), read_register(args.after), datetime.now(timezone.utc).isoformat(timespec="seconds"))
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Live rows: {len(payload['results'])}")


if __name__ == "__main__":
    main()
