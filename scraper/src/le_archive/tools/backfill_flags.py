"""Backfill `_enrichment.{artists,mood}` boolean flags from observed field presence.

The enrichment flags are supposed to mean "this phase has run for this record" —
but throughout the session several phases populated fields without setting the
flag, leaving the facet-side signal out of sync with reality.

Rules applied here (conservative — only ADD true, never flip to false):
  - `_enrichment.artists = true` if `artist_genres` is non-empty.
  - `_enrichment.mood = true` if `mood` is non-empty.
  - `_enrichment.mixcloud = true` if `duration` is set (every mixcloud-enriched
    record gets duration; the flag should mirror that).

Run idempotently as many times as needed. Writes back via `partial_update_object`
to Algolia; raw_sets.json is synced afterward via sync_from_algolia if desired.

Usage:
    poetry run python -m le_archive.tools.backfill_flags [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from le_archive.algolia_client import INDEX_NAME, client as make_client, load_env


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    load_env()
    client = make_client()

    hits: list[dict] = []

    def agg(res):  # noqa: ANN001
        for h in res.hits:
            hits.append(h.to_dict() if hasattr(h, "to_dict") else dict(h))

    client.browse_objects(
        index_name=INDEX_NAME,
        aggregator=agg,
        browse_params={
            "attributesToRetrieve": [
                "objectID",
                "_enrichment",
                "artist_genres",
                "mood",
                "duration",
            ],
        },
    )
    print(f"[backfill] fetched {len(hits)} records")

    updates: list[dict] = []
    stats = {"artists": 0, "mood": 0, "mixcloud": 0}

    for h in hits:
        enr = dict(h.get("_enrichment") or {})
        changed = False

        if h.get("artist_genres") and not enr.get("artists"):
            enr["artists"] = True
            stats["artists"] += 1
            changed = True
        if h.get("mood") and not enr.get("mood"):
            enr["mood"] = True
            stats["mood"] += 1
            changed = True
        if h.get("duration") and not enr.get("mixcloud"):
            enr["mixcloud"] = True
            stats["mixcloud"] += 1
            changed = True

        if changed:
            updates.append({"objectID": h["objectID"], "_enrichment": enr})

    print(
        f"[backfill] would flip: artists={stats['artists']} "
        f"mood={stats['mood']} mixcloud={stats['mixcloud']} "
        f"(total records touched: {len(updates)})"
    )

    if args.dry_run:
        print("[backfill] --dry-run, no writes")
        return 0

    if not updates:
        print("[backfill] nothing to do")
        return 0

    # partial_update_objects → one request per 1000 records.
    for i in range(0, len(updates), 1000):
        batch = updates[i : i + 1000]
        client.partial_update_objects(
            index_name=INDEX_NAME, objects=batch
        )
        print(f"[backfill] pushed {i + len(batch)}/{len(updates)}")

    print("[backfill] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
