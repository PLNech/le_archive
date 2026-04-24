"""Phase 4b — enrich the artist universe with Discogs + Last.fm metadata.

Flow:
1. Walk raw_sets.json, extract the unique set of artist names.
2. For each artist not yet cached in data/artists.json, hit:
   - Discogs  — canonical id, country, styles, profile snippet
   - Last.fm  — top tags (= genre signal), listener count, similar artists
3. Denormalize top tags/genres back into each set record that features the
   artist, then partial_update that set in Algolia so the frontend gets
   `artist_genres` + `artist_countries` facets in real time.

Resumable:
- Per-artist cache in data/artists.json. Skip if already populated.
- Per-set enrichment tracked via record["_enrichment"]["artists"] in raw_sets.json.

Usage:
    poetry run python -m le_archive.enrich_artists [--dry-run] [--limit N] [--delay 1.0]
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

from le_archive._io import atomic_write_json
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from .algolia_client import INDEX_NAME, client as algolia_client, load_env
from .disambiguation import reject as phase_a_reject

ARTISTS_INDEX = "archive_artists"

# Last.fm returns non-genre tags freely; filter these out before denormalizing
# into `artist_genres` so the facet stays music-meaningful.
# Countries + cities + meta-tags + stars-ratings — captured from the audit.
JUNK_TAGS = {
    "seen live", "favorites", "favourites", "favourite",
    "3 stars", "4 stars", "5 stars",
    "male vocalists", "female vocalists", "chillout",
    "netherlands", "united kingdom", "united states",
    "berlin", "amsterdam", "london", "detroit",
    "mixes", "dj", "dj mix", "podcast",
}

ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
OVERRIDES_PATH = ROOT / "scraper" / "data" / "artist_overrides.json"

DISCOGS_BASE = "https://api.discogs.com"
LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "LeArchive/0.1 (+paullouis.nech@algolia.com)"
CHECKPOINT_EVERY = 10  # save caches every N artists


# ----- Discogs -----


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def discogs_search_artist(client: httpx.Client, token: str, name: str) -> dict | None:
    r = client.get(
        f"{DISCOGS_BASE}/database/search",
        params={"q": name, "type": "artist", "token": token, "per_page": 5},
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    results = (r.json().get("results") or [])
    # Prefer exact-title match (case-insensitive); fall back to first result.
    lower = name.lower()
    for item in results:
        if (item.get("title") or "").lower() == lower:
            return item
    return results[0] if results else None


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def discogs_artist_detail(client: httpx.Client, token: str, artist_id: int) -> dict | None:
    r = client.get(f"{DISCOGS_BASE}/artists/{artist_id}", params={"token": token})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


# ----- Last.fm -----


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def lastfm_get(client: httpx.Client, api_key: str, method: str, artist: str) -> dict | None:
    r = client.get(
        LASTFM_BASE,
        params={
            "method": method,
            "artist": artist,
            "api_key": api_key,
            "format": "json",
            "autocorrect": 1,
        },
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    # Last.fm returns {"error": 6, "message": "..."} for missing artists (HTTP 200).
    if isinstance(data, dict) and "error" in data:
        return None
    return data


# ----- Enrichment core -----


def build_artist_record(
    client: httpx.Client,
    discogs_token: str,
    lastfm_key: str,
    name: str,
    delay_s: float,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hit both APIs and return a flattened cache row for this artist.

    `override` lets the caller redirect the search (e.g. "Boris" → "Boris Werner")
    or pin to a specific Discogs artist id. See data/artist_overrides.json.
    """
    row: dict[str, Any] = {"name": name}
    action = (override or {}).get("action") or ""
    query = (override or {}).get("query") or name
    discogs_id = (override or {}).get("discogs_id")

    if action == "skip":
        row["_enriched"] = True
        row["_override_skip"] = True
        return row

    # --- Discogs
    time.sleep(delay_s)
    try:
        if action == "discogs_id" and discogs_id:
            hit = {"id": discogs_id, "uri": f"/artist/{discogs_id}"}
        else:
            hit = discogs_search_artist(client, discogs_token, query)
    except Exception as e:
        hit = None
        row["discogs_error"] = str(e)[:140]
    if hit:
        row["discogs_id"] = hit.get("id")
        row["discogs_url"] = f"https://www.discogs.com{hit.get('uri', '')}"
        time.sleep(delay_s)
        try:
            detail = discogs_artist_detail(client, discogs_token, int(hit["id"]))
        except Exception as e:
            detail = None
            row["discogs_error"] = str(e)[:140]
        if detail:
            # Discogs stores country/profile at artist level; styles live on releases.
            profile = (detail.get("profile") or "").strip()
            if profile:
                row["profile"] = profile[:800]
            namevariations = detail.get("namevariations") or []
            if namevariations:
                row["aliases"] = namevariations[:5]

    # --- Last.fm
    time.sleep(delay_s)
    try:
        info = lastfm_get(client, lastfm_key, "artist.getinfo", query)
    except Exception as e:
        info = None
        row["lastfm_error"] = str(e)[:140]
    if info and "artist" in info:
        a = info["artist"]
        stats = a.get("stats") or {}
        row["lastfm_url"] = a.get("url")
        try:
            row["listeners"] = int(stats.get("listeners") or 0) or None
            row["playcount"] = int(stats.get("playcount") or 0) or None
        except (TypeError, ValueError):
            pass
        tags = ((a.get("tags") or {}).get("tag")) or []
        row["tags"] = [t.get("name") for t in tags if t.get("name")][:8]
        bio = (a.get("bio") or {}).get("summary") or ""
        # Last.fm bios close with a "Read more on Last.fm" anchor; strip it.
        bio = bio.split("<a href")[0].strip()
        if bio:
            row["bio_snippet"] = bio[:400]

    time.sleep(delay_s)
    try:
        sim = lastfm_get(client, lastfm_key, "artist.getsimilar", query)
    except Exception:
        sim = None
    if sim and "similarartists" in sim:
        items = (sim["similarartists"].get("artist")) or []
        row["similar"] = [it.get("name") for it in items if it.get("name")][:8]

    row["_enriched"] = True
    return row


def classify_status(row: dict[str, Any] | None) -> str:
    """`ok` | `partial` | `failed` | `missing` — honest per-artist state."""
    if not row:
        return "missing"
    had_error = bool(row.get("discogs_error") or row.get("lastfm_error"))
    has_tags = bool(row.get("tags"))
    has_discogs = bool(row.get("discogs_id"))
    if had_error and not (has_tags or has_discogs):
        return "failed"
    if has_tags and has_discogs:
        return "ok"
    return "partial"


def derive_set_fields(
    set_artists: list[str],
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate the denormalized fields we write into each set record.

    Includes per-artist status so the frontend can distinguish
    'fully enriched' sets from 'one artist failed, the other is rich'.
    """
    genres: list[str] = []
    similar: list[str] = []
    seen_g: set[str] = set()
    seen_s: set[str] = set()
    status_map: dict[str, str] = {}
    for name in set_artists:
        row = cache.get(name)
        status_map[name] = classify_status(row)
        if not row:
            continue
        # Keep only real genre tags — drop noise ("mixes", "netherlands", ...).
        clean_tags = [t for t in (row.get("tags") or []) if t.lower() not in JUNK_TAGS]
        for t in clean_tags[:3]:
            key = t.lower()
            if key not in seen_g:
                seen_g.add(key)
                genres.append(t)
        for s in (row.get("similar") or [])[:3]:
            key = s.lower()
            if key not in seen_s:
                seen_s.add(key)
                similar.append(s)
    statuses = list(status_map.values())
    if statuses and all(s == "ok" for s in statuses):
        aggregate = "full"
    elif any(s == "ok" or s == "partial" for s in statuses):
        aggregate = "partial"
    else:
        aggregate = "none"
    return {
        "artist_genres": genres[:6],
        "artist_similar": similar[:6],
        "artist_status": aggregate,
        "artist_status_detail": status_map,
    }


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    ARTISTS_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def artist_objectid(name: str) -> str:
    """Deterministic objectID from artist name. Lower-cased, whitespace normalized."""
    return " ".join(name.lower().split())


def to_artist_record(name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Flatten our cache row into an Algolia record for the archive_artists index."""
    obj: dict[str, Any] = {"objectID": artist_objectid(name), "name": name}
    for k in (
        "discogs_id",
        "discogs_url",
        "lastfm_url",
        "listeners",
        "playcount",
        "tags",
        "similar",
        "profile",
        "bio_snippet",
        "aliases",
    ):
        if row.get(k) is not None:
            obj[k] = row[k]
    return obj


def save_sets(records: list[dict[str, Any]]) -> None:
    atomic_write_json(RAW_PATH, records)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Enrich 3 artists and print.")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between API calls (60/min Discogs limit).")
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-process artists whose cached dossier has a `discogs_error` "
        "or `lastfm_error` field. Useful for recovering from transient 5xx.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Flush denormalized set updates to Algolia every N (default 50).",
    )
    args = p.parse_args()

    load_env()
    discogs_token = os.environ.get("DISCOGS_TOKEN")
    lastfm_key = os.environ.get("LASTFM_API_KEY")
    if not discogs_token or not lastfm_key:
        print("[phase4b] missing DISCOGS_TOKEN or LASTFM_API_KEY in .env", file=sys.stderr)
        return 2

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    print(f"[phase4b] loaded {len(records)} sets")

    cache: dict[str, dict[str, Any]] = {}
    if ARTISTS_PATH.exists():
        cache = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    print(f"[phase4b] artist cache: {len(cache)} already enriched")

    overrides: dict[str, dict[str, Any]] = {}
    if OVERRIDES_PATH.exists():
        overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        active = [n for n, o in overrides.items() if (o or {}).get("action")]
        print(f"[phase4b] overrides loaded: {len(overrides)} entries, {len(active)} active")

    all_artists: list[str] = []
    seen: set[str] = set()
    for r in records:
        for a in (r.get("artists") or []):
            if a and a not in seen:
                seen.add(a)
                all_artists.append(a)
    print(f"[phase4b] {len(all_artists)} unique artists across archive")

    def is_pending(a: str) -> bool:
        row = cache.get(a)
        if row is None or not row.get("_enriched"):
            return True
        if args.retry_failed and (row.get("discogs_error") or row.get("lastfm_error")):
            return True
        # Audit cleared this dossier; re-run under --retry-failed (Phase A will
        # now gate obvious wrong-matches). Active overrides also trigger re-run.
        if row.get("_cleared_by_audit") and (
            args.retry_failed or (overrides.get(a) or {}).get("action")
        ):
            return True
        # Phase A previously rejected this dossier; re-run if blacklist changed.
        if row.get("_phase_a_rejected") and args.retry_failed:
            return True
        return False

    todo = [a for a in all_artists if is_pending(a)]
    mode = "retry-failed" if args.retry_failed else "fresh"
    print(f"[phase4b] {len(todo)} artists pending enrichment ({mode})")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[phase4b] --limit → processing {len(todo)}")

    algolia = None if args.dry_run else algolia_client()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as http:
        if args.dry_run:
            for name in todo[:3]:
                row = build_artist_record(
                    http, discogs_token, lastfm_key, name, args.delay,
                    override=overrides.get(name),
                )
                print(json.dumps({name: row}, ensure_ascii=False, indent=2))
            return 0

        since_checkpoint = 0
        pending_set_updates: dict[str, dict[str, Any]] = {}
        pending_artist_rows: list[dict[str, Any]] = []

        def flush_batches() -> None:
            if pending_set_updates:
                try:
                    algolia.partial_update_objects(
                        index_name=INDEX_NAME,
                        objects=list(pending_set_updates.values()),
                    )
                except Exception as e:
                    tqdm.write(f"  algolia partial_update batch fail: {e}")
                pending_set_updates.clear()
            if pending_artist_rows:
                try:
                    algolia.save_objects(
                        index_name=ARTISTS_INDEX, objects=pending_artist_rows
                    )
                except Exception as e:
                    tqdm.write(f"  algolia save_objects (artists) batch fail: {e}")
                pending_artist_rows.clear()

        for name in tqdm(todo, desc="artists"):
            try:
                row = build_artist_record(
                    http, discogs_token, lastfm_key, name, args.delay,
                    override=overrides.get(name),
                )
            except Exception as e:
                tqdm.write(f"  fail {name}: {e}")
                continue

            # Phase A disambiguation gate — reject obvious wrong-person matches
            # (k-pop / metal / pre-2016 death dates). Only skip the gate when an
            # override is in play — the user has already hand-picked the target.
            if not (overrides.get(name) or {}).get("action"):
                rejected, reason = phase_a_reject(row)
                if rejected:
                    tqdm.write(f"  phase-A reject {name}: {reason}")
                    row = {
                        "name": name,
                        "_enriched": True,
                        "_phase_a_rejected": True,
                        "_rejection_reason": reason,
                    }

            cache[name] = row

            # Fan out denormalized fields to every set featuring this artist.
            # Accumulate updates (keyed by objectID so late updates for the same
            # set overwrite earlier ones — always the latest-derived state).
            affected = [r for r in records if name in (r.get("artists") or [])]
            for r in affected:
                derived = derive_set_fields(r.get("artists") or [], cache)
                r.setdefault("_enrichment", {})["artists"] = True
                for k, v in derived.items():
                    r[k] = v
                pending_set_updates[r["objectID"]] = {
                    "objectID": r["objectID"],
                    **derived,
                    "_enrichment": r["_enrichment"],
                }

            pending_artist_rows.append(to_artist_record(name, cache[name]))

            if (
                len(pending_set_updates) >= args.batch_size
                or len(pending_artist_rows) >= args.batch_size
            ):
                flush_batches()

            since_checkpoint += 1
            if since_checkpoint >= CHECKPOINT_EVERY:
                save_cache(cache)
                save_sets(records)
                since_checkpoint = 0

        flush_batches()

    save_cache(cache)
    save_sets(records)
    enriched = sum(1 for r in cache.values() if r.get("_enriched"))
    with_tags = sum(1 for r in cache.values() if (r.get("tags") or []))
    print(
        f"[phase4b] done — {enriched} artists enriched, {with_tags} with last.fm tags"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
