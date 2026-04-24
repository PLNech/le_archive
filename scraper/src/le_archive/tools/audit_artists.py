"""Artist dossier audit — catch wrong-artist matches in artists.json.

Symptom that motivated this tool: the "Boris" playing De School (a Dutch
techno DJ, Boris Werner) got matched to a Japanese sludge/drone band on
Discogs+Last.fm. enrich_artists.py picked the top-1 result by string match,
with no context filter. Common names (Boris, John, Lee, Mark, ...) are
probably all at risk.

This runs an LLM over (set_context, enriched_dossier) tuples and asks it
to judge whether the dossier plausibly belongs to an electronic/dance/
underground artist playing a 2016–2024 Amsterdam club with mostly
techno/house/ambient programming. Output lands in
`data/artist_audit.json`, one row per audited artist, with `verdict`,
`confidence`, `reason`, and a `hint` at what the correct match might be.

Resumable: per-artist rows are keyed by artist name; re-runs skip already
judged rows unless `--force`. Cheap enough ($2ish on ~380 artists) to
re-run with a better prompt after calibration.

Usage:
    # calibration pass on 20 artists
    poetry run python -m le_archive.tools.audit_artists --limit 20

    # full pass
    poetry run python -m le_archive.tools.audit_artists
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from le_archive._io import atomic_write_json
from le_archive.algolia_client import load_env

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
AUDIT_PATH = ROOT / "scraper" / "data" / "artist_audit.json"

BASE_URL = "https://inference.api.enablers.algolia.net/v1"
CHECKPOINT_EVERY = 10


SYSTEM_PROMPT = """You are a music archivist verifying artist metadata for
De School Amsterdam (2016–2024), a Dutch underground club known for techno,
house, electro, ambient, experimental, leftfield, breaks, dub, and adjacent
electronic genres. Line-ups skewed European (Dutch, Berlin, UK) with
international guests; occasional hip-hop/jazz/eclectic nights exist but are
the exception.

You receive:
- artist_name (as it appears in the archive)
- set_context: dates, spaces, events, co-artists — the archive's own evidence
- enriched_dossier: what enrich_artists.py resolved (Discogs/Last.fm tags,
  bio, similar artists, listeners)

Judge whether the dossier plausibly matches the artist who played these
sets. Return strict JSON:

  verdict:     "likely_correct" | "likely_wrong" | "uncertain"
  confidence:  integer 0–10 (how sure you are about the verdict)
  reason:      one sentence explaining the mismatch or match signal
  hint:        one short phrase with the likely-correct artist (or "" if
               verdict=likely_correct or you can't tell). Include aliases
               or disambiguators the scraper could use, e.g. "Boris Werner"
               or "Carista (DJ)" or "not the Berlin rapper".

Heuristics:
- Dossier tags dominated by rock/metal/hip-hop/country/pop while the set
  context is pure techno/house events → likely_wrong.
- Dossier bio says "classical pianist" / "Japanese sludge band" while the
  artist DJs 2-hour closing sets at De Club → likely_wrong.
- Dossier tags include techno/house/electronic/ambient/experimental
  overlapping with context → likely_correct.
- Context is ambiguous (one-off eclectic event, NYE, "all-nighter") and
  dossier is plausible → uncertain.
- No dossier tags and no bio but the name matches a known DJ (you may
  recognize from the name + space) → uncertain, hint if helpful.

Be decisive when evidence is strong. Use "uncertain" sparingly.
"""

USER_PROMPT_TEMPLATE = """Artist: "{name}"

Set context (De School Amsterdam):
{context}

Enriched dossier (from Discogs + Last.fm):
{dossier}

Return only the JSON object."""


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.5, min=2, max=20),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
def call_llm(client: httpx.Client, token: str, model: str, user_blob: str) -> dict[str, Any]:
    r = client.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_blob},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_tokens": 300,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    body = r.json()
    if "choices" not in body:
        err = body.get("error", {}).get("message") or json.dumps(body)[:300]
        raise httpx.HTTPStatusError(err, request=r.request, response=r)
    return json.loads(body["choices"][0]["message"]["content"])


def build_set_context(artist: str, sets: list[dict[str, Any]]) -> str:
    """Compact set-context blob: at most 5 representative sets + aggregates."""
    if not sets:
        return "  (no sets found in archive — unusual; dossier likely orphan)"
    chosen = sorted(sets, key=lambda s: s.get("date_ts") or 0)
    picks: list[dict[str, Any]] = []
    if len(chosen) <= 5:
        picks = chosen
    else:
        picks = [chosen[0], chosen[len(chosen) // 2], chosen[-1]]
        picks.append(chosen[len(chosen) // 4])
        picks.append(chosen[3 * len(chosen) // 4])
        picks = sorted({s["objectID"]: s for s in picks}.values(), key=lambda s: s.get("date_ts") or 0)

    spaces = Counter(s.get("space") or "—" for s in sets).most_common(3)
    events = Counter(s.get("event") or "—" for s in sets).most_common(3)
    coartists = Counter()
    for s in sets:
        for a in s.get("artists") or []:
            if a != artist:
                coartists[a] += 1
    top_co = coartists.most_common(5)

    lines: list[str] = [f"- Total sets in archive: {len(sets)}"]
    lines.append(f"- Spaces: {', '.join(f'{sp} ({n})' for sp, n in spaces)}")
    lines.append(f"- Events: {', '.join(f'{e} ({n})' for e, n in events)}")
    if top_co:
        lines.append(f"- Frequent co-artists: {', '.join(f'{a} ({n})' for a, n in top_co)}")
    else:
        lines.append("- Frequent co-artists: (solo appearances only)")
    lines.append("- Representative sets:")
    for s in picks:
        line = f"    · {s.get('date')} · {s.get('space','—')} · {s.get('event','—')}"
        tags = s.get("tags") or []
        if tags:
            line += f"  tags=[{', '.join(tags[:4])}]"
        lines.append(line)
    return "\n".join(lines)


def build_dossier(row: dict[str, Any] | None) -> str:
    if not row:
        return "  (no dossier — unresolved)"
    lines: list[str] = []
    if row.get("discogs_url"):
        lines.append(f"- discogs_url: {row['discogs_url']}")
    if row.get("lastfm_url"):
        lines.append(f"- lastfm_url: {row['lastfm_url']}")
    if row.get("listeners") is not None:
        lines.append(f"- lastfm_listeners: {row['listeners']}")
    tags = row.get("tags") or []
    if tags:
        lines.append(f"- tags: {', '.join(tags[:8])}")
    aliases = row.get("aliases") or []
    if aliases:
        lines.append(f"- aliases (Discogs namevariations): {', '.join(aliases[:5])}")
    similar = row.get("similar") or []
    if similar:
        lines.append(f"- similar (Last.fm): {', '.join(similar[:8])}")
    bio = (row.get("bio_snippet") or row.get("profile") or "").strip()
    if bio:
        lines.append(f"- bio/profile: {bio[:500]}")
    if row.get("discogs_error") or row.get("lastfm_error"):
        lines.append(
            f"- errors: discogs={row.get('discogs_error','')}; lastfm={row.get('lastfm_error','')}"
        )
    if not lines:
        return "  (empty dossier — enrichment produced nothing)"
    return "\n".join(lines)


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    v = raw.get("verdict")
    if v not in ("likely_correct", "likely_wrong", "uncertain"):
        v = "uncertain"
    out["verdict"] = v
    c = raw.get("confidence")
    if isinstance(c, (int, float)):
        out["confidence"] = max(0, min(10, int(round(c))))
    else:
        out["confidence"] = 5
    reason = raw.get("reason")
    out["reason"] = reason[:400] if isinstance(reason, str) else ""
    hint = raw.get("hint")
    out["hint"] = hint[:200] if isinstance(hint, str) else ""
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default="medium", choices=["medium", "large"])
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument("--dry-run", action="store_true", help="print 3 blobs, call LLM, show response.")
    p.add_argument("--force", action="store_true", help="re-audit artists already in audit file.")
    p.add_argument(
        "--only-untagged",
        action="store_true",
        help="skip dossiers whose Last.fm tags already look electronic "
        "(fast calibration on suspect cases only).",
    )
    args = p.parse_args()

    load_env()
    token = os.environ.get("ENABLERS_TOKEN")
    if not token:
        print("[audit] missing ENABLERS_TOKEN in .env", file=sys.stderr)
        return 2

    artists = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    sets = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    print(f"[audit] loaded {len(artists)} artists, {len(sets)} sets")

    by_artist: dict[str, list[dict[str, Any]]] = {}
    for s in sets:
        for a in s.get("artists") or []:
            by_artist.setdefault(a, []).append(s)

    existing: dict[str, dict[str, Any]] = {}
    if AUDIT_PATH.exists():
        existing = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        print(f"[audit] {len(existing)} artists already audited; resuming")

    electronic_tags = {
        "techno", "house", "electronic", "electronica", "deep house", "tech house",
        "ambient", "minimal", "minimal techno", "acid", "dub techno", "drum and bass",
        "dnb", "idm", "electro", "breakbeat", "breaks", "downtempo", "trance",
        "leftfield", "experimental electronic", "disco", "garage", "dubstep",
        "bass music", "industrial", "dub",
    }

    def is_pending(name: str) -> bool:
        if name in existing and not args.force:
            return False
        if args.only_untagged:
            tags = {t.lower() for t in (artists.get(name, {}).get("tags") or [])}
            if tags & electronic_tags:
                return False
        return True

    todo = [a for a in artists if is_pending(a)]
    print(f"[audit] {len(todo)} artists pending")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[audit] --limit → processing {len(todo)}")

    results: dict[str, dict[str, Any]] = dict(existing)

    with httpx.Client(timeout=60.0) as http:
        if args.dry_run:
            for name in todo[:3]:
                row = artists.get(name) or {}
                ctx = build_set_context(name, by_artist.get(name, []))
                dossier = build_dossier(row)
                blob = USER_PROMPT_TEMPLATE.format(name=name, context=ctx, dossier=dossier)
                print("=" * 70)
                print(blob)
                raw = call_llm(http, token, args.model, blob)
                print("\nverdict:", json.dumps(raw, ensure_ascii=False, indent=2))
                time.sleep(args.delay)
            return 0

        since_checkpoint = 0
        for name in tqdm(todo, desc="audit"):
            row = artists.get(name) or {}
            ctx = build_set_context(name, by_artist.get(name, []))
            dossier = build_dossier(row)
            blob = USER_PROMPT_TEMPLATE.format(name=name, context=ctx, dossier=dossier)
            try:
                raw = call_llm(http, token, args.model, blob)
                verdict = validate(raw)
            except Exception as e:
                tqdm.write(f"  fail {name}: {e}")
                continue
            verdict["n_sets"] = len(by_artist.get(name, []))
            verdict["has_dossier"] = bool(row.get("_enriched"))
            results[name] = verdict

            since_checkpoint += 1
            if since_checkpoint >= CHECKPOINT_EVERY:
                atomic_write_json(AUDIT_PATH, results)
                since_checkpoint = 0
            time.sleep(args.delay)

    atomic_write_json(AUDIT_PATH, results)

    # Summary
    verdicts = Counter(v.get("verdict", "?") for v in results.values())
    wrong_hi_conf = [
        (n, v) for n, v in results.items()
        if v.get("verdict") == "likely_wrong" and v.get("confidence", 0) >= 7
    ]
    print(f"[audit] done — {len(results)} total")
    print(f"  verdicts: {dict(verdicts)}")
    print(f"  high-confidence wrong ({len(wrong_hi_conf)}):")
    for n, v in sorted(wrong_hi_conf, key=lambda kv: -kv[1].get("confidence", 0))[:20]:
        print(f"    · {n} (conf {v['confidence']}) → {v.get('hint') or v.get('reason','')[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
