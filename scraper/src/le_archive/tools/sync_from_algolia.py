"""Reverse resync: pull every record from Algolia → overwrite raw_sets.json.

Needed after sharded P6 runs (which don't write raw_sets.json to avoid race
conditions). Algolia becomes the authoritative source; this script brings
the local file back in line so downstream enrichers (enrich_mood, audit,
etc.) see the current state.

Usage:
    poetry run python -m le_archive.tools.sync_from_algolia
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from le_archive._io import atomic_write_json
from le_archive.algolia_client import INDEX_NAME, client as make_client, load_env

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"


def main() -> int:
    load_env()
    client = make_client()

    hits: list[dict] = []

    def agg(res):  # noqa: ANN001
        for h in res.hits:
            hits.append(h.to_dict() if hasattr(h, "to_dict") else dict(h))

    client.browse_objects(
        index_name=INDEX_NAME, aggregator=agg, browse_params={}
    )
    print(f"[sync] pulled {len(hits)} records from {INDEX_NAME}")

    # Drop Algolia-specific objectID-only bookkeeping that might clash with
    # local-only keys. Keep everything else.
    for h in hits:
        h.pop("_highlightResult", None)
        h.pop("_rankingInfo", None)

    # Sort by objectID for a stable file on disk.
    hits.sort(key=lambda h: h.get("objectID", ""))

    if RAW_PATH.exists():
        backup = RAW_PATH.with_suffix(".json.bak")
        backup.write_bytes(RAW_PATH.read_bytes())
        print(f"[sync] backed up previous raw_sets.json → {backup.name}")

    atomic_write_json(RAW_PATH, hits)

    audio_done = sum(1 for h in hits if (h.get("_enrichment") or {}).get("audio"))
    mood_done = sum(1 for h in hits if (h.get("_enrichment") or {}).get("mood"))
    mood_populated = sum(1 for h in hits if h.get("mood"))
    print(
        f"[sync] wrote {len(hits)} → raw_sets.json "
        f"(audio={audio_done}, _enrichment.mood={mood_done}, mood field populated={mood_populated})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
