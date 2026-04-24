"""Compare text-only vs multimodal mood classification on a sample of sets.

Both modes hit the llm-enablers-api `medium` (qwen3.5-35b-fp8, multimodal),
with the same metadata blob. Multimodal adds a viz_fingerprint PNG.

Output: JSON records {objectID, text_only: {...}, multimodal: {...}} +
a compact stdout table so the eye can spot disagreements.

Usage:
    poetry run python -m le_archive.tools.eval_multimodal_mood [--limit 10]
        [--out data/eval_multimodal_mood.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from le_archive.algolia_client import load_env
from le_archive.enrich_mood import (
    build_blob,
    call_llm,
    validate_mood,
)
from le_archive.fingerprint_image import fingerprint_to_data_uri

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
DEFAULT_OUT = ROOT / "scraper" / "data" / "eval_multimodal_mood.json"


def fmt_mood(m: dict[str, Any]) -> str:
    moods = ",".join((m.get("mood") or [])[:3]) or "—"
    return (
        f"e{m.get('energy','?'):>2} · f{m.get('focus_score','?'):>2} · "
        f"{m.get('tempo_bucket','—'):<4} · {moods}"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--delay", type=float, default=0.3)
    args = p.parse_args()

    load_env()
    token = os.environ.get("ENABLERS_TOKEN")
    if not token:
        print("[eval] ENABLERS_TOKEN missing", file=sys.stderr)
        return 2

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    artist_cache = (
        json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
        if ARTISTS_PATH.exists()
        else {}
    )

    sample = [
        r
        for r in records
        if (r.get("_enrichment") or {}).get("audio")
        and (r.get("viz_fingerprint") or {}).get("data_b64")
    ][: args.limit]
    print(f"[eval] {len(sample)} sets with local audio + fingerprint")

    results: list[dict[str, Any]] = []
    header = f"{'id':<48} | {'text-only':<40} | {'multimodal':<40}"
    print(header)
    print("-" * len(header))

    with httpx.Client(timeout=60.0) as http:
        for r in sample:
            blob = build_blob(r, artist_cache)
            try:
                text_raw = call_llm(http, token, "medium", blob)
                text_clean = validate_mood(text_raw)
            except Exception as e:  # noqa: BLE001
                text_clean = {"error": str(e)[:120]}
            time.sleep(args.delay)

            try:
                img = fingerprint_to_data_uri(r["viz_fingerprint"])
                mm_raw = call_llm(
                    http, token, "medium", blob, image_data_uri=img
                )
                mm_clean = validate_mood(mm_raw)
            except Exception as e:  # noqa: BLE001
                mm_clean = {"error": str(e)[:120]}
            time.sleep(args.delay)

            results.append(
                {
                    "objectID": r["objectID"],
                    "artists": r.get("artists"),
                    "date": r.get("date"),
                    "text_only": text_clean,
                    "multimodal": mm_clean,
                }
            )

            oid = r["objectID"][:46]
            print(
                f"{oid:<48} | {fmt_mood(text_clean):<40} | {fmt_mood(mm_clean):<40}"
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n[eval] wrote {len(results)} comparisons → {args.out}")

    disagree = sum(
        1
        for r in results
        if set((r["text_only"].get("mood") or []))
        != set((r["multimodal"].get("mood") or []))
    )
    print(f"[eval] mood disagreement: {disagree}/{len(results)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
