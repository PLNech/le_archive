"""Data-quality audit across our enrichment outputs.

Run after any enrichment pass to surface records that look wrong. Outputs a
tree of buckets, each listing suspicious objectIDs with a one-line reason.

    poetry run python -m le_archive.tools.audit [--sample N]

Checks performed:
  * bpm out of plausible range (60..200) or zero — librosa fooled by beatless sets.
  * energy_mean at extremes (0.0 or >0.35) — likely silent stream or decoder error.
  * mood assigned with no audio features — blind P5 output that should be re-run.
  * artist_status=='none' but `artist_genres` populated — stale denormalization.
  * dossier has both discogs_error and no tags — true failure, candidate for --retry-failed.
  * Last.fm tags that are obviously not genres ("seen live", "3 stars", country names).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ..algolia_client import load_env


ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"

NON_GENRE_TAGS = {
    "seen live", "favorites", "favourites", "favourite",
    "3 stars", "4 stars", "5 stars",
    "male vocalists", "female vocalists", "chillout",
    "netherlands", "united kingdom", "united states",
    "berlin", "amsterdam", "london", "detroit",
    "mixes", "dj", "dj mix", "podcast",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=5, help="Show up to N examples per bucket.")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = p.parse_args()

    load_env()
    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    dossiers = (
        json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
        if ARTISTS_PATH.exists()
        else {}
    )

    buckets: dict[str, list[str]] = defaultdict(list)

    for r in records:
        oid = r.get("objectID", "?")
        enr = r.get("_enrichment") or {}
        has_audio = bool(enr.get("audio"))
        has_mood = bool(enr.get("mood"))

        bpm = r.get("bpm")
        if has_audio and bpm is not None and (bpm < 60 or bpm > 200):
            buckets["bpm_out_of_range"].append(f"{oid}  bpm={bpm}")
        if has_audio and bpm is not None and bpm == 0:
            buckets["bpm_zero"].append(oid)

        energy = r.get("energy_mean")
        if has_audio and energy is not None and (energy <= 0 or energy > 0.4):
            buckets["energy_extreme"].append(f"{oid}  energy={energy}")

        if has_mood and not has_audio:
            buckets["mood_blind"].append(
                f"{oid}  (mood set without audio features)"
            )

        status = r.get("artist_status")
        genres = r.get("artist_genres") or []
        if status == "none" and genres:
            buckets["stale_artist_genres"].append(
                f"{oid}  status=none but {len(genres)} genres present"
            )

        if enr.get("mixcloud") and not r.get("cover_url"):
            buckets["mixcloud_no_cover"].append(oid)

    for name, row in dossiers.items():
        if not row.get("_enriched"):
            continue
        had_error = bool(row.get("discogs_error") or row.get("lastfm_error"))
        has_tags = bool(row.get("tags"))
        has_discogs = bool(row.get("discogs_id"))
        if had_error and not (has_tags or has_discogs):
            buckets["dossier_failed"].append(
                f"{name}  err={row.get('discogs_error') or row.get('lastfm_error')}"
            )
        tags = (row.get("tags") or [])
        junk = [t for t in tags if t.lower() in NON_GENRE_TAGS]
        if junk:
            buckets["junk_tags"].append(f"{name}  junk={junk}")

    totals = {k: len(v) for k, v in buckets.items()}

    if args.json:
        out = {"totals": totals, "examples": {k: v[: args.sample] for k, v in buckets.items()}}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if not buckets:
        print("[audit] no issues surfaced")
        return 0

    print("=== Audit report ===\n")
    for bucket, entries in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        print(f"{bucket}: {len(entries)}")
        for e in entries[: args.sample]:
            print(f"  {e}")
        if len(entries) > args.sample:
            print(f"  … +{len(entries) - args.sample} more")
        print()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
