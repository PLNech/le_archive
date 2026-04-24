"""Phase 4a — enrich sets with Mixcloud API metadata.

For each record with mixcloud_url, fetch api.mixcloud.com/{path}/ and extract:
  duration, play_count, favorite_count, comment_count, mixcloud_tags,
  tracklist (first 30 sections), cover_url.

Writes back to the same raw_sets.json. Idempotent via _enrichment.mixcloud flag.

Usage:
    poetry run python -m le_archive.enrich_mixcloud [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from le_archive._io import atomic_write_json
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm


RAW_PATH = Path(__file__).resolve().parents[3] / "scraper" / "data" / "raw_sets.json"
API_BASE = "https://api.mixcloud.com"
USER_AGENT = "LeArchive enricher (contact paullouis.nech@algolia.com)"


def to_api_path(mixcloud_url: str) -> str | None:
    """Turn https://www.mixcloud.com/DSAMS/slug/ into /DSAMS/slug/"""
    u = urlparse(mixcloud_url)
    if "mixcloud.com" not in (u.netloc or ""):
        return None
    path = u.path
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def _bucket(duration_s: int | None) -> str | None:
    if not duration_s:
        return None
    if duration_s < 30 * 60:
        return "short"
    if duration_s < 120 * 60:
        return "medium"
    return "long"


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def fetch_api(client: httpx.Client, path: str) -> dict | None:
    r = client.get(f"{API_BASE}{path}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def enrich_one(client: httpx.Client, record: dict, delay_s: float) -> dict:
    """Return record with fields populated. Mutates in place too."""
    if record.get("_enrichment", {}).get("mixcloud"):
        return record
    mx = record.get("mixcloud_url")
    if not mx:
        return record
    path = to_api_path(mx)
    if not path:
        return record
    time.sleep(delay_s)
    data = fetch_api(client, path)
    if data is None:
        record["_enrichment"]["mixcloud"] = True  # negative cache
        record["mixcloud_missing"] = True
        return record

    duration = int(data.get("audio_length", 0)) or None
    record["duration"] = duration
    record["duration_bucket"] = _bucket(duration)
    record["play_count"] = int(data.get("play_count", 0) or 0)
    record["favorite_count"] = int(data.get("favorite_count", 0) or 0)
    record["mixcloud_tags"] = [t["name"] for t in (data.get("tags") or [])]
    pics = data.get("pictures") or {}
    record["cover_url"] = pics.get("large") or pics.get("medium")

    sections = (data.get("sections") or [])[:30]
    record["tracklist"] = [
        {
            "start_time": s.get("start_time"),
            "track_artist": ((s.get("track") or {}).get("artist") or {}).get("name"),
            "track_title": (s.get("track") or {}).get("name"),
        }
        for s in sections
    ]
    record["_enrichment"]["mixcloud"] = True
    return record


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=1.0)
    args = p.parse_args()

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    print(f"[phase4a] loaded {len(records)} records")

    todo = [r for r in records if not r.get("_enrichment", {}).get("mixcloud")]
    print(f"[phase4a] {len(todo)} not yet enriched")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[phase4a] limit → processing {len(todo)}")

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
    ) as client:
        if args.dry_run:
            sample = todo[:3]
            for r in sample:
                enrich_one(client, r, args.delay)
                print(json.dumps(r, ensure_ascii=False, indent=2))
            return 0

        ok = 0
        miss = 0
        for r in tqdm(todo, desc="mixcloud"):
            try:
                enrich_one(client, r, args.delay)
                if r.get("mixcloud_missing"):
                    miss += 1
                else:
                    ok += 1
            except Exception as e:
                tqdm.write(f"  fail {r['objectID']}: {e}")

    atomic_write_json(RAW_PATH, records)
    print(f"[phase4a] enriched {ok}, missing {miss}, total {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
