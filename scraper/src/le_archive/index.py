"""Phase 2 — push raw_sets.json records to Algolia.

Usage:
    poetry run python -m le_archive.index [--dry-run] [--batch 1000]

Idempotent: upserts by objectID. Safe to re-run after enrichment phases
re-write the raw file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from algoliasearch.search.client import SearchClientSync

from le_archive.algolia_client import INDEX_NAME, client as make_client


RAW_PATH = Path(__file__).resolve().parents[3] / "scraper" / "data" / "raw_sets.json"


def load_records() -> list[dict]:
    if not RAW_PATH.exists():
        raise SystemExit(
            f"{RAW_PATH} not found — run `poetry run python -m le_archive.scrape` first."
        )
    return json.loads(RAW_PATH.read_text(encoding="utf-8"))


def push(client: SearchClientSync, records: list[dict], batch_size: int) -> None:
    total = len(records)
    for start in range(0, total, batch_size):
        chunk = records[start : start + batch_size]
        resp = client.save_objects(index_name=INDEX_NAME, objects=chunk)
        # `save_objects` returns a list of BatchResponse in v4
        for br in resp:
            client.wait_for_task(index_name=INDEX_NAME, task_id=br.task_id)
        print(f"  pushed {min(start + batch_size, total)}/{total}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--batch", type=int, default=1000)
    args = p.parse_args()

    records = load_records()
    print(f"[phase2] loaded {len(records)} records from {RAW_PATH.name}")

    if args.dry_run:
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
        return 0

    c = make_client()
    push(c, records, args.batch)
    print(f"[phase2] index '{INDEX_NAME}' now has {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
