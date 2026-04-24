"""Apply artist-audit verdicts: clear wrongly-matched dossiers.

Input: `data/artist_audit.json` produced by `audit_artists.py`.

For each artist flagged `likely_wrong` with confidence above the threshold,
we:
  1. Clear the dossier in `data/artists.json` — keep only `name` and an
     audit-trail marker. The Discogs / Last.fm / bio fields vanish.
  2. Rebuild `archive_artists` record so the frontend dossier modal hits
     "not-found" and falls back to search links.
  3. Re-derive `artist_genres` / `artist_similar` / `artist_status` for
     every set that featured this artist. Co-artist-derived values survive.
  4. Push set updates + artist minimal records to Algolia.

Safe by default: writes minimal data, doesn't try to guess a replacement.
Pair with `artist_overrides.json` (hand-curated) for targeted re-enrichment.

Usage:
    poetry run python -m le_archive.tools.apply_audit --dry-run
    poetry run python -m le_archive.tools.apply_audit --threshold 7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tqdm import tqdm

from le_archive._io import atomic_write_json
from le_archive.algolia_client import INDEX_NAME, client as algolia_client
from le_archive.enrich_artists import (
    ARTISTS_INDEX,
    derive_set_fields,
    to_artist_record,
)

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
AUDIT_PATH = ROOT / "scraper" / "data" / "artist_audit.json"
OVERRIDES_TEMPLATE_PATH = ROOT / "scraper" / "data" / "artist_overrides.template.json"


def clear_dossier(name: str, verdict: dict[str, Any]) -> dict[str, Any]:
    """Minimal cache row — name + audit marker. Drops every external-source field."""
    return {
        "name": name,
        "_enriched": True,
        "_cleared_by_audit": True,
        "audit_verdict": verdict.get("verdict"),
        "audit_confidence": verdict.get("confidence"),
        "audit_reason": verdict.get("reason"),
        "audit_hint": verdict.get("hint"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=int, default=7, help="min confidence to act on (default 7).")
    p.add_argument("--dry-run", action="store_true", help="print what would change; don't write.")
    p.add_argument("--batch-size", type=int, default=100)
    args = p.parse_args()

    if not AUDIT_PATH.exists():
        print(f"[apply_audit] no audit file at {AUDIT_PATH} — run audit_artists first", file=sys.stderr)
        return 2

    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    artists = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))

    to_clear = {
        name: v
        for name, v in audit.items()
        if v.get("verdict") == "likely_wrong" and v.get("confidence", 0) >= args.threshold
    }
    print(f"[apply_audit] {len(to_clear)} artists to clear (threshold={args.threshold})")

    if not to_clear:
        return 0

    print("\nPreview:")
    for name, v in sorted(to_clear.items(), key=lambda kv: -kv[1]["confidence"])[:20]:
        hint = v.get("hint") or ""
        print(f"  [{v['confidence']:2}] {name[:30]:30} → {hint[:70]}")

    if args.dry_run:
        # Also emit the overrides template so user can start curating.
        template = {
            name: {
                "note": v.get("hint") or v.get("reason"),
                "action": "",  # fill with "search_as" | "discogs_id" | "skip"
                "query": "",
                "discogs_id": None,
            }
            for name, v in sorted(to_clear.items())
        }
        print(f"\n[apply_audit] --dry-run: would write overrides template to {OVERRIDES_TEMPLATE_PATH}")
        print(f"  ({len(template)} entries)")
        return 0

    # 1. Clear dossiers in cache
    for name, v in to_clear.items():
        artists[name] = clear_dossier(name, v)

    # 2. Rebuild artist_genres / similar / status for affected sets
    affected_set_updates: list[dict[str, Any]] = []
    for r in tqdm(records, desc="re-derive sets"):
        set_artists = r.get("artists") or []
        if not any(a in to_clear for a in set_artists):
            continue
        derived = derive_set_fields(set_artists, artists)
        for k, v in derived.items():
            r[k] = v
        affected_set_updates.append({"objectID": r["objectID"], **derived})

    print(f"[apply_audit] {len(affected_set_updates)} sets to repush")

    # 3. Rebuild artist records
    artist_records = [to_artist_record(name, artists[name]) for name in to_clear]

    # 4. Push to Algolia in batches
    algolia = algolia_client()
    for i in range(0, len(affected_set_updates), args.batch_size):
        batch = affected_set_updates[i : i + args.batch_size]
        algolia.partial_update_objects(index_name=INDEX_NAME, objects=batch)
    for i in range(0, len(artist_records), args.batch_size):
        batch = artist_records[i : i + args.batch_size]
        # save_objects replaces the record — which is what we want for cleared rows.
        algolia.save_objects(index_name=ARTISTS_INDEX, objects=batch)

    # 5. Persist
    atomic_write_json(ARTISTS_PATH, artists)
    atomic_write_json(RAW_PATH, records)

    # 6. Write overrides template for user curation
    template = {
        name: {
            "note": v.get("hint") or v.get("reason"),
            "action": "",
            "query": "",
            "discogs_id": None,
        }
        for name, v in sorted(to_clear.items())
    }
    OVERRIDES_TEMPLATE_PATH.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"[apply_audit] cleared {len(to_clear)} dossiers, "
        f"repushed {len(affected_set_updates)} sets, "
        f"wrote overrides template to {OVERRIDES_TEMPLATE_PATH.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
