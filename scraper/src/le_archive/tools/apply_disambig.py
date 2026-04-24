"""Sweep existing artist dossiers through the disambiguation gate.

Why standalone: `enrich_artists.py` runs the gate during the per-artist
build loop, but rows that already passed under Layer A aren't re-fetched
on `--retry-failed`. When Layer B (or any new rule) ships, we need a
one-shot pass that re-evaluates every cached dossier — no Discogs or
Last.fm calls needed, the tags+bio are already in the cache.

For each newly-rejected dossier, we:
  1. Clear the cache row to a minimal `_phase_a_rejected` stub.
  2. Re-derive `artist_genres` / `artist_similar` / `artist_status` for
     every set that featured the artist (co-artist values survive).
  3. Push set updates + minimal artist records to Algolia.

Usage:
    poetry run python -m le_archive.tools.apply_disambig --dry-run
    poetry run python -m le_archive.tools.apply_disambig
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from tqdm import tqdm

from le_archive._io import atomic_write_json
from le_archive.algolia_client import INDEX_NAME, client as algolia_client
from le_archive.disambiguation import reject as disambig_reject
from le_archive.enrich_artists import (
    ARTISTS_INDEX,
    derive_set_fields,
    to_artist_record,
)

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"


def clear_dossier(name: str, reason: str) -> dict[str, Any]:
    """Minimal cache row — keep only the name + rejection marker."""
    return {
        "name": name,
        "_enriched": True,
        "_phase_a_rejected": True,
        "_rejection_reason": reason,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="preview; don't write.")
    p.add_argument("--batch-size", type=int, default=100)
    args = p.parse_args()

    artists = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))

    n_sets_per_artist: Counter[str] = Counter()
    for r in records:
        for a in r.get("artists") or []:
            n_sets_per_artist[a] += 1

    # Evaluate every currently-kept dossier through the gate.
    newly_rejected: dict[str, str] = {}
    already_rejected = 0
    for name, row in artists.items():
        if row.get("_phase_a_rejected"):
            already_rejected += 1
            continue
        rejected, reason = disambig_reject(
            row, n_sets_for_artist=n_sets_per_artist.get(name, 0)
        )
        if rejected:
            newly_rejected[name] = reason

    print(
        f"[apply_disambig] {len(artists)} dossiers total, "
        f"{already_rejected} already rejected, "
        f"{len(newly_rejected)} newly rejected by current rules"
    )

    if not newly_rejected:
        return 0

    print("\nPreview:")
    for name, reason in sorted(newly_rejected.items()):
        print(f"  {name:30} → {reason}")

    if args.dry_run:
        return 0

    # 1. Clear dossiers
    for name, reason in newly_rejected.items():
        artists[name] = clear_dossier(name, reason)

    # 2. Re-derive affected sets
    affected_set_updates: list[dict[str, Any]] = []
    for r in tqdm(records, desc="re-derive sets"):
        set_artists = r.get("artists") or []
        if not any(a in newly_rejected for a in set_artists):
            continue
        derived = derive_set_fields(set_artists, artists)
        for k, v in derived.items():
            r[k] = v
        affected_set_updates.append({"objectID": r["objectID"], **derived})

    print(f"[apply_disambig] {len(affected_set_updates)} sets to repush")

    # 3. Minimal artist records (save_objects replaces, which is correct here)
    artist_records = [to_artist_record(name, artists[name]) for name in newly_rejected]

    # 4. Push to Algolia
    algolia = algolia_client()
    for i in range(0, len(affected_set_updates), args.batch_size):
        algolia.partial_update_objects(
            index_name=INDEX_NAME,
            objects=affected_set_updates[i : i + args.batch_size],
        )
    for i in range(0, len(artist_records), args.batch_size):
        algolia.save_objects(
            index_name=ARTISTS_INDEX, objects=artist_records[i : i + args.batch_size]
        )

    # 5. Persist
    atomic_write_json(ARTISTS_PATH, artists)
    atomic_write_json(RAW_PATH, records)

    print(
        f"[apply_disambig] cleared {len(newly_rejected)} dossiers, "
        f"repushed {len(affected_set_updates)} sets"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
