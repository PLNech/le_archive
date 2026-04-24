"""Rule-based filters for catching obvious wrong-artist matches.

Audit (audit_artists.py) showed ~32% of resolved dossiers were the wrong
person — common names (Boris, Danielle, Cleveland, Orson Wells) picked
up unrelated celebrities because enrich_artists picked the top-1 Discogs
or Last.fm hit. This module holds the cheap, deterministic filters that
run on fetched metadata BEFORE we commit the dossier, catching the most
common failure modes without another API call.

Layer A (instant wins, no API cost):
    1. Genre blacklist: tag-based hard reject for genres De School never
       programs (k-pop, death metal, medieval, country, ...).
    2. Lifespan gate: regex the bio for "(YYYY–YYYY)" spans. If the
       artist's end year predates De School's opening (2016), reject.

Layer B (tuned against LLM ground truth, still no API cost):
    3. Tag polarity: a recurring booking (n_sets ≥ 2) whose Last.fm top-3
       tags show no electronic/club signal is almost always a name
       collision (wrong Julie — shoegaze; wrong Remma — indie). Measured
       100% precision / 5% recall on the 2026-04-24 audit.

Layer C (future — adds Discogs API calls):
    4. Release-style scoring: fetch top-N Discogs candidates, pick the
       one whose releases skew most electronic.

Use: pass a freshly-built dossier row through `reject(row, n_sets)` → it
returns (True, reason) to drop the dossier, or (False, "") to keep it.
`n_sets` is optional; without it, only Layer A fires.
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

# Positive markers: tags that vouch for an electronic / club booking. If the
# artist's top-3 Last.fm tags contain ANY of these, Layer B stays out of the
# way — the dossier is plausibly the right person.
#
# Kept generous on purpose — false negatives (letting wrong matches through)
# are cheaper than false positives (rejecting real De School bookings).
ELECTRONIC_POSITIVE: frozenset[str] = frozenset({
    # techno / house / club backbone
    "techno", "house", "deep house", "tech house", "minimal", "minimal techno",
    "acid", "acid techno", "acid house", "electro", "electroclash",
    "electronic", "electronica", "idm", "club",
    # ambient / leftfield
    "ambient", "dark ambient", "drone", "leftfield", "experimental electronic",
    "downtempo", "trip hop", "post-dubstep",
    # bass / dub / garage family
    "dub", "dub techno", "dubstep", "uk garage", "garage", "grime",
    "bass music", "breakbeat", "breaks", "drum and bass", "dnb", "jungle",
    "footwork", "future garage", "neurofunk",
    # disco / industrial / adjacent
    "disco", "italo disco", "nu disco", "italo", "industrial", "ebm",
    "synthwave", "darkwave",
    # rave / hardcore spectrum (De School books this)
    "trance", "psytrance", "goa trance", "hard trance", "hardcore",
    "gabber", "nu gabber", "rave", "hardstyle",
    # global club
    "uk funky", "afrobeat", "baile funk", "kuduro", "gqom", "broken beat",
    "ghettotech", "ghetto tech", "booty bass",
    # hip-hop adjacencies (De School programs cloud rap, experimental hip-hop)
    "hip-hop", "hip hop", "cloud rap",
})


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


def _has_electronic_tag(tags: list[str] | None, top_n: int = 3) -> bool:
    """Does the artist's top-N Last.fm tags contain any electronic/club marker?"""
    if not tags:
        return False
    return any(t.lower() in ELECTRONIC_POSITIVE for t in tags[:top_n])


def _tag_polarity_reject(
    row: dict[str, Any], n_sets_for_artist: int
) -> tuple[bool, str]:
    """Layer B signal: recurring booking with no electronic tag = wrong person.

    Fires only when we have enough signal to be confident:
    - artist has n≥2 sets in the archive (real booking pattern, not one-off)
    - Last.fm returned ≥3 tags (we have tag data to reason about)
    - top-3 tags contain no electronic/club marker

    Measured on 2026-04-24 audit ground truth: 100% precision, ~5% recall
    of remaining wrong matches. A no-regret filter.
    """
    MIN_SETS = 2
    MIN_TAGS = 3
    if n_sets_for_artist < MIN_SETS:
        return False, ""
    tags = row.get("tags") or []
    if len(tags) < MIN_TAGS:
        return False, ""
    if _has_electronic_tag(tags, top_n=3):
        return False, ""
    return (
        True,
        f"n_sets={n_sets_for_artist}, top-3 tags {tags[:3]} show no electronic signal",
    )


def reject(
    row: dict[str, Any], n_sets_for_artist: int | None = None
) -> tuple[bool, str]:
    """Return (True, reason) if disambiguation rejects this dossier.

    Runs Layer A (blacklist + lifespan) always; Layer B (tag polarity)
    only when `n_sets_for_artist` is provided. Caller should clear the
    dossier to a minimal record when rejected, keeping only the name so
    the frontend falls back to search links.
    """
    tag_hits = _tag_blacklist_hit(row.get("tags"))
    if tag_hits:
        return True, f"blacklisted tags: {sorted(tag_hits)}"

    bio = row.get("bio_snippet") or row.get("profile") or ""
    death = _dead_before_archive(bio)
    if death is not None:
        return True, f"lifespan ends {death}, pre-archive (opened {ARCHIVE_OPENED_YEAR})"

    if n_sets_for_artist is not None:
        rejected, reason = _tag_polarity_reject(row, n_sets_for_artist)
        if rejected:
            return True, f"tag polarity: {reason}"

    return False, ""
