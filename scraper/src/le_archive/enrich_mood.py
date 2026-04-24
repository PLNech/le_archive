"""Phase 5 — LLM mood tagging via Algolia's llm-enablers-api gateway.

For each set without `_enrichment.mood=true`, we gather:
  - artists (+ their cached bios and Last.fm tags from artists.json)
  - event, space, date
  - P6 audio features (bpm, brightness, energy_mean, noisiness) when available

…and ask an LLM to classify with a closed vocabulary, returning structured JSON:
  {
    "mood": ["ambient", "deep"],           # 1–5 from closed vocab
    "energy": 3,                           # 1–10
    "tempo_bucket": "slow" | "mid" | "fast",
    "focus_score": 8,                      # 1–10, ability to soundtrack focus work
    "reasoning": "…"                       # 1 sentence, audit trail
  }

Gateway: `https://inference.api.enablers.algolia.net/v1` (OpenAI-compatible).
Auth: bearer token in `ENABLERS_TOKEN`.
Model alias: `medium` by default (fast). `large` = MiniMax-M2.5 (196k context).

Usage:
    poetry run python -m le_archive.enrich_mood [--dry-run] [--limit N]
        [--model medium|large] [--delay 0.3]
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
from .fingerprint_image import fingerprint_to_data_uri


ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
CHECKPOINT_EVERY = 10

BASE_URL = "https://inference.api.enablers.algolia.net/v1"

MOOD_VOCAB = [
    "ambient", "dub", "deep", "atmospheric", "breaks", "electro", "acid",
    "industrial", "peak-time", "hard", "trance", "dnb", "house", "disco",
    "downtempo", "experimental", "jazz", "leftfield", "bass", "rhythmic",
]

SYSTEM_PROMPT = f"""You are a seasoned music archivist classifying DJ sets from
De School Amsterdam (2016–2024). Return strict JSON matching this schema:

  mood:          array of 1–5 lowercase labels chosen ONLY from this closed
                 vocabulary (no synonyms, no new terms):
                 {", ".join(MOOD_VOCAB)}
  energy:        integer 1–10, 1 = near-silent ambient, 10 = peak-time hard
  tempo_bucket:  "slow" (<110 bpm) | "mid" (110–130) | "fast" (>130)
  focus_score:   integer 1–10, ability of this set to soundtrack focused work;
                 10 = atmospheric/deep/ambient, 1 = relentless peak-time
  reasoning:     one short sentence — why you chose these labels

Honour the audio features if present (bpm, energy_mean in 0..1, brightness,
noisiness) over loose vibes. When the set has no audio features, use the
artists' genre tags and bios as the primary signal.
"""

USER_PROMPT_TEMPLATE = """Set metadata:
{blob}

Return only the JSON object."""


VISION_ADDENDUM = """
You will also receive a PNG image: a 24-band mel-spectrogram covering the whole
set (low freq at bottom, time left-to-right, magma palette — brighter = louder).
Use its shape to inform the classification:
- flat low-band presence with sparse high-band spikes → ambient/downtempo
- dense bright bands across the image → peak-time/hard/industrial
- a clear low-to-bright buildup curve → trance/breaks/progressive
- narrow brightness (mid-band only) → house/deep/dub
"""


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.5, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def call_llm(
    client: httpx.Client,
    token: str,
    model: str,
    blob: str,
    image_data_uri: str | None = None,
) -> dict[str, Any]:
    # System prompt is identical across calls — mark it cacheable. OpenAI-proto
    # servers that don't understand `cache_control` ignore the field silently;
    # Anthropic-proxied ones (and some MiniMax setups) honour it for ~80% input
    # cost reduction on repeated calls.
    sys_text = SYSTEM_PROMPT + (VISION_ADDENDUM if image_data_uri else "")
    system_block = [
        {"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}
    ]
    text_user = USER_PROMPT_TEMPLATE.format(blob=blob)
    if image_data_uri:
        user_content: Any = [
            {"type": "text", "text": text_user},
            {"type": "image_url", "image_url": {"url": image_data_uri}},
        ]
    else:
        user_content = text_user

    r = client.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_block},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_tokens": 400,
        },
        timeout=60.0,
    )
    if r.status_code >= 400:
        # Fall back to plain string system prompt if the server rejects the
        # structured cache_control form (some OpenAI-proto servers do).
        if r.status_code in (400, 422):
            r = client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_text},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 400,
                },
                timeout=60.0,
            )
    r.raise_for_status()
    body = r.json()
    if "choices" not in body:
        # Gateway sometimes returns 200 with {"error": {...}}.
        err = body.get("error", {}).get("message") or json.dumps(body)[:300]
        raise httpx.HTTPStatusError(err, request=r.request, response=r)
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def build_blob(record: dict[str, Any], artist_cache: dict[str, dict[str, Any]]) -> str:
    """Compact metadata blob for the LLM. Keep < 2KB."""
    parts: list[str] = []
    parts.append(f"- Artists: {', '.join(record.get('artists') or []) or '—'}")
    parts.append(f"- Event: {record.get('event', '—')}")
    parts.append(f"- Space: {record.get('space', '—')}  (De School Amsterdam)")
    parts.append(f"- Date: {record.get('date', '—')}  ({record.get('weekday','')})")
    if record.get("is_b2b"):
        parts.append("- Format: back-to-back")

    for a in (record.get("artists") or [])[:4]:
        row = artist_cache.get(a) or {}
        tags = (row.get("tags") or [])[:5]
        bio = (row.get("bio_snippet") or row.get("profile") or "")[:220]
        if tags or bio:
            parts.append(f"- Artist “{a}”")
            if tags:
                parts.append(f"    tags: {', '.join(tags)}")
            if bio:
                parts.append(f"    bio:  {bio}")

    if record.get("_enrichment", {}).get("audio"):
        bpm = record.get("bpm")
        energy = record.get("energy_mean")
        brightness = record.get("brightness")
        noisiness = record.get("noisiness")
        parts.append("- Audio features (from librosa on full audio):")
        if bpm is not None:
            parts.append(f"    bpm: {bpm:.0f}")
        if energy is not None:
            parts.append(f"    energy_mean: {energy:.3f}  (0=silent, 1=peak)")
        if brightness is not None:
            parts.append(f"    brightness: {brightness:.3f}  (higher = airy)")
        if noisiness is not None:
            parts.append(f"    noisiness: {noisiness:.3f}")

    return "\n".join(parts)


def validate_mood(out: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate. Keep only vocab entries; clamp numerics."""
    cleaned: dict[str, Any] = {}
    mood = out.get("mood") or []
    if isinstance(mood, str):
        mood = [mood]
    cleaned["mood"] = [m for m in mood if isinstance(m, str) and m in MOOD_VOCAB][:5]

    energy = out.get("energy")
    if isinstance(energy, (int, float)):
        cleaned["energy"] = max(1, min(10, int(round(energy))))

    tb = out.get("tempo_bucket")
    if tb in ("slow", "mid", "fast"):
        cleaned["tempo_bucket"] = tb

    focus = out.get("focus_score")
    if isinstance(focus, (int, float)):
        cleaned["focus_score"] = max(1, min(10, int(round(focus))))

    reasoning = out.get("reasoning")
    if isinstance(reasoning, str):
        cleaned["reasoning"] = reasoning[:280]

    return cleaned


def save_sets(records: list[dict[str, Any]]) -> None:
    atomic_write_json(RAW_PATH, records)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="process 3 sets, print JSON.")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default="medium", choices=["medium", "large"])
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument(
        "--allow-blind",
        action="store_true",
        help="Allow classification on sets without audio features. Default is "
        "to gate on `_enrichment.audio:true` so mood tags are grounded in "
        "librosa features rather than guessed from artist bios alone.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich even sets that already have `_enrichment.mood:true`. "
        "Use this after audio features become available for sets that were "
        "previously mood-tagged from bio alone.",
    )
    p.add_argument(
        "--with-fingerprint",
        action="store_true",
        help="Multimodal mode: render viz_fingerprint to PNG and send to a "
        "vision-capable model alongside the text blob. Requires the set to "
        "have a viz_fingerprint (sets without are skipped with a warning).",
    )
    args = p.parse_args()

    if args.with_fingerprint and args.model == "large":
        print(
            "[phase5] --with-fingerprint requires a multimodal model; forcing --model medium",
            file=sys.stderr,
        )
        args.model = "medium"

    load_env()
    token = os.environ.get("ENABLERS_TOKEN")
    if not token:
        print("[phase5] missing ENABLERS_TOKEN in .env", file=sys.stderr)
        return 2

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    print(f"[phase5] loaded {len(records)} sets")

    artist_cache: dict[str, dict[str, Any]] = {}
    if ARTISTS_PATH.exists():
        artist_cache = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    print(f"[phase5] artist cache: {len(artist_cache)} dossiers available")

    def pending(r: dict[str, Any]) -> bool:
        enr = r.get("_enrichment", {}) or {}
        already = bool(enr.get("mood"))
        has_audio = bool(enr.get("audio"))
        if args.force:
            # Re-enrich only sets whose audio is now available but mood was
            # previously classified blind — or everything if --allow-blind.
            return has_audio or args.allow_blind
        if already:
            return False
        if args.allow_blind:
            return True
        return has_audio

    todo = [r for r in records if pending(r)]
    gated = "audio-gated" if not args.allow_blind else "blind-allowed"
    print(f"[phase5] {len(todo)} sets pending mood enrichment ({gated})")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[phase5] --limit → processing {len(todo)}")

    algolia = None if args.dry_run else algolia_client()

    def fingerprint_uri_for(r: dict[str, Any]) -> str | None:
        fp = r.get("viz_fingerprint") or {}
        if not fp.get("data_b64"):
            return None
        try:
            return fingerprint_to_data_uri(fp)
        except Exception as e:  # noqa: BLE001
            tqdm.write(f"  fingerprint render fail {r['objectID']}: {e}")
            return None

    with httpx.Client(timeout=60.0) as http:
        if args.dry_run:
            for r in todo[:3]:
                blob = build_blob(r, artist_cache)
                img = fingerprint_uri_for(r) if args.with_fingerprint else None
                print("=" * 60)
                print(blob)
                if args.with_fingerprint:
                    print(
                        "image:",
                        f"{len(img)} chars" if img else "(no fingerprint — skipping image)",
                    )
                raw = call_llm(http, token, args.model, blob, image_data_uri=img)
                cleaned = validate_mood(raw)
                print("\nraw :", json.dumps(raw, ensure_ascii=False))
                print("clean:", json.dumps(cleaned, ensure_ascii=False))
                time.sleep(args.delay)
            return 0

        since_checkpoint = 0
        ok = 0
        fail = 0
        for r in tqdm(todo, desc="mood"):
            try:
                blob = build_blob(r, artist_cache)
                img = (
                    fingerprint_uri_for(r) if args.with_fingerprint else None
                )
                if args.with_fingerprint and not img:
                    tqdm.write(
                        f"  skip {r['objectID']}: --with-fingerprint but no viz_fingerprint"
                    )
                    fail += 1
                    continue
                raw = call_llm(http, token, args.model, blob, image_data_uri=img)
                mood = validate_mood(raw)
            except Exception as e:
                tqdm.write(f"  fail {r['objectID']}: {e}")
                fail += 1
                continue

            if not mood.get("mood"):
                # Empty vocab match — skip writing the flag so a retry can fix later.
                fail += 1
                continue

            r.update({k: v for k, v in mood.items() if k != "reasoning"})
            r["mood_reasoning"] = mood.get("reasoning")
            r.setdefault("_enrichment", {})["mood"] = True
            ok += 1

            update = {
                "objectID": r["objectID"],
                "mood": r.get("mood"),
                "energy": r.get("energy"),
                "tempo_bucket": r.get("tempo_bucket"),
                "focus_score": r.get("focus_score"),
                "mood_reasoning": r.get("mood_reasoning"),
                "_enrichment": r["_enrichment"],
            }
            try:
                algolia.partial_update_object(
                    index_name=INDEX_NAME,
                    object_id=r["objectID"],
                    attributes_to_update=update,
                )
            except Exception as e:
                tqdm.write(f"  algolia partial_update fail for {r['objectID']}: {e}")

            since_checkpoint += 1
            if since_checkpoint >= CHECKPOINT_EVERY:
                save_sets(records)
                since_checkpoint = 0
            time.sleep(args.delay)

    save_sets(records)
    print(f"[phase5] done — {ok} tagged, {fail} failed/empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
