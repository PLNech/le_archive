"""Phase 9 — track identification via Chromaprint + AcoustID.

For each set with _enrichment.audio=true (so we trust the audio URL + have
some analysis to anchor against), download via yt-dlp, fingerprint with
`fpcalc` in overlapping windows, look up each window via AcoustID
/v2/lookup, merge adjacent same-track hits, write a `tracklist` field.

AcoustID returns MusicBrainz recording IDs; we denormalize the first
artist-name + title into the tracklist entry and also stash the mbid for
deep-linking later.

Realistic expectations:
  * DJ sets are full of unreleased edits / white labels / unreleased IDs
    → ~25% of minutes identified, rest returns confidence < threshold.
  * AcoustID rate limit is 3 req/s (generous for 886 × ~30 windows).
  * Free API key is per-application, not per-user.

Ethics: only derived track IDs + timestamps are stored. No audio retained.
Same rationale as P6.

Prereqs:
  * `sudo apt install chromaprint-tools` for the `fpcalc` CLI.
  * `poetry add pyacoustid` (installed as of 2026-04-22).
  * `ACOUSTID_KEY` in repo `.env`.

Usage:
    poetry run python -m le_archive.enrich_tracks [--limit N] [--dry-run]
    poetry run python -m le_archive.enrich_tracks --shard 0/2   # parallel
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any

import acoustid
from tqdm import tqdm

from le_archive._io import atomic_write_json
from le_archive.algolia_client import INDEX_NAME, client as make_client


RAW_PATH = Path(__file__).resolve().parents[3] / "scraper" / "data" / "raw_sets.json"
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
TMP_ROOT = Path(tempfile.gettempdir()) / "learchive-tracks"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

# AcoustID throttles at 3 req/s → sleep ~0.34s between lookups.
LOOKUP_DELAY = 0.4
# Window size for fpcalc. AcoustID's matcher needs ≥30s, recommended ~60-90s.
WINDOW_SEC = 60
# Overlap so we don't miss a track that straddles a window boundary.
WINDOW_STEP = 45
# Confidence floor: AcoustID returns 0..1 scores; below this → ignore.
MIN_SCORE = 0.5
# Merge two consecutive hits of the same recording if gap <= this many seconds.
MERGE_GAP_SEC = 120


def load_env() -> None:
    """Read .env without the dotenv package, picking only keys we need."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def download_audio(url: str, dst_stem: Path, timeout: int = 900) -> Path | None:
    """Download bestaudio via yt-dlp, native codec. Same pattern as P6."""
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-progress",
        "--no-warnings",
        "--no-cache-dir",
        "--concurrent-fragments", "4",
        "-f", "bestaudio",
        "-o", f"{dst_stem}.%(ext)s",
        "--print", "after_move:filepath",
        url,
    ]
    try:
        r = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    printed = (r.stdout or "").strip().splitlines()
    if printed:
        p = Path(printed[-1])
        if p.exists():
            return p
    for cand in dst_stem.parent.iterdir():
        if cand.name.startswith(dst_stem.name + "."):
            return cand
    return None


def fingerprint_window(
    audio_path: Path, start: int, length: int
) -> tuple[int, str] | None:
    """fpcalc over a time-bounded slice. Returns (duration, fingerprint-str)."""
    cmd = [
        "fpcalc",
        "-raw",
        "-length", str(length),
        "-ts", str(start),  # fpcalc doesn't have -start; instead use ffmpeg
    ]
    # fpcalc can't slice itself; pipe via ffmpeg.
    ff = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-ss", str(start),
        "-t", str(length),
        "-i", str(audio_path),
        "-f", "wav",
        "-ac", "1",
        "-ar", "22050",
        "-",
    ]
    try:
        p1 = subprocess.Popen(ff, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # fpcalc accepts - for stdin when given no file arg
        p2 = subprocess.run(
            ["fpcalc", "-raw", "-"],
            stdin=p1.stdout,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if p1.stdout:
            p1.stdout.close()
        p1.wait(timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p2.returncode != 0:
        return None
    duration = 0
    fingerprint = ""
    for line in p2.stdout.splitlines():
        if line.startswith("DURATION="):
            duration = int(line.split("=", 1)[1])
        elif line.startswith("FINGERPRINT="):
            fingerprint = line.split("=", 1)[1]
    if not fingerprint:
        return None
    return duration, fingerprint


def lookup(
    api_key: str, duration: int, fingerprint: str
) -> list[dict[str, Any]]:
    """AcoustID lookup. Returns flattened list of candidate recordings."""
    try:
        # pyacoustid wraps the REST call; returns (score, rec_id, title, artist)
        matches = list(acoustid.match(api_key, None, (fingerprint, duration)))
    except acoustid.WebServiceError:
        return []
    except Exception:
        return []
    out = []
    for score, rec_id, title, artist in matches:
        if not rec_id or score < MIN_SCORE:
            continue
        out.append({
            "score": float(score),
            "mbid": rec_id,
            "title": title or "",
            "artist": artist or "",
        })
    return out


def merge_tracklist(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse consecutive window-hits into track entries.

    `hits` is time-ordered. Each has: {start_sec, mbid, title, artist, score}.
    Adjacent entries with the same mbid get merged into one entry with the
    earliest start_sec and max score.
    """
    out: list[dict[str, Any]] = []
    for h in hits:
        if out and out[-1]["mbid"] == h["mbid"] and (
            h["start_sec"] - out[-1]["start_sec"] <= MERGE_GAP_SEC
        ):
            out[-1]["score"] = max(out[-1]["score"], h["score"])
            continue
        out.append(dict(h))
    return out


def process_one(
    record: dict[str, Any], api_key: str, verbose: bool = False
) -> list[dict[str, Any]] | None:
    object_id = record["objectID"]
    url = record.get("mixcloud_url")
    if not url:
        return None
    duration_total = record.get("duration") or 0
    if duration_total < WINDOW_SEC:
        return []  # too short to fingerprint reasonably

    stem = TMP_ROOT / object_id
    audio_path: Path | None = None
    try:
        if verbose:
            tqdm.write(f"  [{object_id}] downloading…")
        audio_path = download_audio(url, stem)
        if audio_path is None:
            tqdm.write(f"  [{object_id}] yt-dlp failed")
            return None

        windows: list[tuple[int, int]] = []
        t = 0
        while t + WINDOW_SEC <= duration_total:
            windows.append((t, WINDOW_SEC))
            t += WINDOW_STEP
        if verbose:
            tqdm.write(f"  [{object_id}] {len(windows)} windows over {duration_total}s")

        hits: list[dict[str, Any]] = []
        for start, length in windows:
            fp = fingerprint_window(audio_path, start, length)
            if fp is None:
                continue
            dur, fingerprint = fp
            candidates = lookup(api_key, dur, fingerprint)
            time.sleep(LOOKUP_DELAY)
            # Take highest-confidence candidate per window.
            if candidates:
                best = max(candidates, key=lambda c: c["score"])
                hits.append({
                    "start_sec": start,
                    **best,
                })

        return merge_tracklist(hits)
    except Exception as e:
        tqdm.write(f"  [{object_id}] FAIL: {type(e).__name__}: {e}")
        return None
    finally:
        if audio_path is not None and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="process 1 set, print tracklist, no save/push")
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--shard",
        type=str,
        default="0/1",
        help="cooperative partition as I/N (0-indexed). See enrich_audio.",
    )
    args = p.parse_args()

    try:
        i_str, n_str = args.shard.split("/", 1)
        shard_i, shard_n = int(i_str), int(n_str)
        if shard_n < 1 or shard_i < 0 or shard_i >= shard_n:
            raise ValueError
    except ValueError:
        print(f"[phase9] bad --shard {args.shard!r}", file=sys.stderr)
        return 2

    load_env()
    api_key = os.environ.get("ACOUSTID_KEY")
    if not api_key:
        print("[phase9] ACOUSTID_KEY missing in .env", file=sys.stderr)
        return 2

    # Prereq check: fpcalc binary
    try:
        r = subprocess.run(["fpcalc", "-version"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            raise OSError
    except (OSError, subprocess.TimeoutExpired):
        print(
            "[phase9] `fpcalc` not found. Install: sudo apt install chromaprint-tools",
            file=sys.stderr,
        )
        return 2

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    todo = [
        r for r in records
        if r.get("mixcloud_url")
        and (r.get("_enrichment") or {}).get("audio")
        and not (r.get("_enrichment") or {}).get("tracks")
    ]
    if shard_n > 1:
        todo = [
            r for r in todo
            if zlib.crc32(r["objectID"].encode("utf-8")) % shard_n == shard_i
        ]
    todo.sort(key=lambda r: r.get("duration") or 99_999)

    shard_tag = f" (shard {shard_i}/{shard_n})" if shard_n > 1 else ""
    print(f"[phase9] {len(todo)} sets pending track ID (shortest first){shard_tag}")
    if args.limit:
        todo = todo[: args.limit]
    if args.dry_run:
        todo = todo[:1]

    algolia = None if args.dry_run else make_client()
    write_raw = shard_n == 1 and not args.dry_run

    ok = failed = empty = 0
    for r in tqdm(todo, desc="tracks"):
        tracklist = process_one(r, api_key, args.verbose)
        if tracklist is None:
            failed += 1
            continue
        if not tracklist:
            empty += 1
            # Still mark as attempted so we don't retry indefinitely on
            # every sweep — unreleased sets legitimately return nothing.
        ok += 1

        r["tracklist"] = tracklist
        r.setdefault("_enrichment", {})["tracks"] = True

        if algolia is not None:
            try:
                algolia.partial_update_object(
                    index_name=INDEX_NAME,
                    object_id=r["objectID"],
                    attributes_to_update={
                        "tracklist": tracklist,
                        "_enrichment": r["_enrichment"],
                    },
                )
            except Exception as e:
                tqdm.write(f"  [{r['objectID']}] algolia update failed: {e}")

        if write_raw:
            atomic_write_json(RAW_PATH, records)

    print(f"[phase9] done: {ok} processed ({empty} empty-tracklist unreleased), {failed} failed")
    if args.dry_run and ok and todo:
        print(json.dumps(todo[0].get("tracklist"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
