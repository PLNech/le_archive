"""Rule-based filters for catching obvious wrong-artist matches.

Audit (audit_artists.py) showed ~32% of resolved dossiers were the wrong
person — common names (Boris, Danielle, Cleveland, Orson Wells) picked
up unrelated celebrities because enrich_artists picked the top-1 Discogs
or Last.fm hit. This module holds the cheap, deterministic filters that
run on fetched metadata BEFORE we commit the dossier, catching the most
common failure modes without another API call.

Layer A (implemented here — instant wins, no API cost):
    1. Genre blacklist: tag-based hard reject for genres De School never
       programs (k-pop, death metal, medieval, country, ...).
    2. Lifespan gate: regex the bio for "(YYYY–YYYY)" spans. If the
       artist's end year predates De School's opening (2016), reject.

Layer B (future — real improvement, adds Discogs API calls):
    3. Release-style scoring: fetch top-N Discogs candidates, pick the
       one whose releases skew most electronic.
    4. Co-artist prior: require Last.fm `similar` to overlap with
       already-resolved De School artists (the archive's own roster).

Use: pass a freshly-built dossier row through `reject(row)` → it returns
(True, reason) to drop the dossier, or (False, "") to keep it.
"""

from __future__ import annotations

import re
from typing import Any

# Genres De School never programs. If ANY of these appears in the artist's
# top 6 Last.fm tags (lowercased), reject as wrong-person match.
#
# We deliberately omit borderline genres (cloud rap, experimental, ambient,
# jazz — all plausible at De School). Only hard disqualifiers go here.
NON_ELECTRONIC_BLACKLIST: frozenset[str] = frozenset({
    # pop / vocal traditions
    "k-pop", "kpop", "j-pop", "jpop", "c-pop", "chanson",
    "country", "bluegrass", "honky tonk",
    "gospel", "christian rock", "worship",
    "musical theatre", "musical", "broadway", "eurovision",
    "opera", "operatic",
    # rock / metal (De School is not a metal club)
    "death metal", "black metal", "pagan black metal", "doom metal",
    "sludge", "sludge metal", "stoner metal", "stoner rock",
    "metalcore", "deathcore", "grindcore", "metal",
    "hardcore punk", "street punk", "crust punk",
    "nu metal", "alternative metal", "symphonic metal",
    "post-rock", "prog rock", "progressive rock", "math rock",
    "alternative rock", "grunge", "emo", "screamo",
    # regional traditional (not rooted in electronic culture)
    "classical", "baroque", "medieval", "renaissance",
    "folk rock", "celtic", "flamenco", "tango",
    # soul / r&b (De School does not book R&B vocalists)
    "r&b", "soul", "motown", "neo-soul", "contemporary r&b",
    # misc vocal-led forms
    "yodeling", "mariachi", "barbershop",
})

# Match "(1939–2024)", "(1939-1985)", "(1939 – 1985)", etc.
# Only triggers on a proper span (not a single-year birth tag).
LIFESPAN_RE = re.compile(r"\((\d{4})\s*[–\-]\s*(\d{4})\)")

ARCHIVE_OPENED_YEAR = 2016


def _tag_blacklist_hit(tags: list[str] | None) -> set[str]:
    """Only check the top-3 tags — Last.fm orders by vote weight, and a
    blacklisted tag at rank 4+ is often a single user's miscategorisation,
    not signal. Checking top-6 costs ~1.7% false positives on our corpus."""
    if not tags:
        return set()
    return {t.lower() for t in tags[:3]} & NON_ELECTRONIC_BLACKLIST


def _dead_before_archive(bio: str | None) -> int | None:
    """Return the death year if the bio contains a completed lifespan
    ending before the archive era. None if no match or still alive."""
    if not bio:
        return None
    m = LIFESPAN_RE.search(bio)
    if not m:
        return None
    birth, death = int(m.group(1)), int(m.group(2))
    if death < ARCHIVE_OPENED_YEAR and birth < death:
        return death
    return None


def reject(row: dict[str, Any]) -> tuple[bool, str]:
    """Return (True, reason) if Layer A rejects this dossier as wrong match.

    Caller should clear the dossier to a minimal record when rejected,
    keeping only the name so the frontend falls back to search links.
    """
    tag_hits = _tag_blacklist_hit(row.get("tags"))
    if tag_hits:
        return True, f"blacklisted tags: {sorted(tag_hits)}"

    bio = row.get("bio_snippet") or row.get("profile") or ""
    death = _dead_before_archive(bio)
    if death is not None:
        return True, f"lifespan ends {death}, pre-archive (opened {ARCHIVE_OPENED_YEAR})"

    return False, ""
