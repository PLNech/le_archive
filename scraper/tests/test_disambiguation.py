"""Smoke tests for Layer A disambiguation rules.

These fixtures are hand-crafted from real wrong-matches seen in the
2026-04-24 LLM audit. If the rules reject the wrong ones and keep the
controls, the layer earns its keep.
"""

from __future__ import annotations

from le_archive.disambiguation import reject


# --- Wrong matches (must reject) ---

def test_rejects_japanese_sludge_boris() -> None:
    row = {
        "tags": ["drone", "Stoner Rock", "experimental", "Sludge", "doom metal"],
        "bio_snippet": "Boris is a Japanese experimental metal band formed in Tokyo in 1992.",
    }
    rejected, reason = reject(row)
    assert rejected, "Boris (Japanese sludge) must be rejected"
    # "sludge" is at rank 4 — top-3 check catches stoner rock instead, also fine.
    assert "stoner rock" in reason.lower() or "sludge" in reason.lower()


def test_rejects_orson_welles_film_director() -> None:
    # No blacklisted tag — we want the death-gate to be what rejects him.
    row = {
        "tags": ["experimental", "film"],
        "bio_snippet": "George Orson Welles (1915–1985) was an American actor, director, "
                       "producer, and screenwriter.",
    }
    rejected, reason = reject(row)
    assert rejected, "Orson Welles (died 1985) must be rejected"
    assert "1985" in reason


def test_rejects_danielle_kpop() -> None:
    row = {
        "tags": ["All", "pop", "k-pop", "australia", "Kpop"],
        "bio_snippet": "Danielle Marsh, known mononymously as DANIELLE is a South Korean-Australian "
                       "singer who is a former-member of the girl group NewJeans.",
    }
    rejected, _ = reject(row)
    assert rejected, "Danielle (k-pop) must be rejected"


def test_rejects_post_rock_c() -> None:
    row = {
        "tags": ["post-rock", "Czech", "math rock", "instrumental", "silver rocket"],
        "bio_snippet": "C are Patrik C., Tommy C., Pepe C. — post-punk band from Prague.",
    }
    rejected, _ = reject(row)
    assert rejected


def test_rejects_medieval_qntal() -> None:
    row = {
        "tags": ["medieval", "darkwave", "Gothic", "electronic", "ethereal"],
        "bio_snippet": "QNTAL are a German medieval music project founded in 1991.",
    }
    rejected, _ = reject(row)
    assert rejected, "QNTAL must be rejected for medieval tag, even with electronic present"


# --- Correct matches (must NOT reject) ---

def test_keeps_rroxymore() -> None:
    row = {
        "tags": ["techno", "electronic", "House", "experimental", "france"],
        "bio_snippet": "rRoxymore is the project of Berlin-based French producer Hermione Frank.",
    }
    rejected, _ = reject(row)
    assert not rejected


def test_keeps_objekt_with_dubstep_tag() -> None:
    # "dubstep" is not on the blacklist — correctly kept.
    row = {
        "tags": ["techno", "dubstep", "electronic", "idm", "bass music"],
        "bio_snippet": "Objekt is TJ Hertz, a techno producer based in Berlin.",
    }
    rejected, _ = reject(row)
    assert not rejected


def test_keeps_makam_with_jazz_tag() -> None:
    # Jazz is deliberately NOT blacklisted; De School books jazz-inflected DJs.
    row = {
        "tags": ["jazz", "electronic", "experimental", "ambient"],
        "bio_snippet": "Makam is a Dutch producer working at the intersection of jazz and house.",
    }
    rejected, _ = reject(row)
    assert not rejected


def test_keeps_empty_row() -> None:
    """Empty dossier is not our problem — don't reject what we know nothing about."""
    rejected, _ = reject({"name": "unknown"})
    assert not rejected


def test_ignores_birth_year_without_end() -> None:
    """(1985) alone is a birth year, not a lifespan — must not trigger death gate."""
    row = {"tags": [], "bio_snippet": "Jane Doe (1985) is a DJ based in Amsterdam."}
    rejected, _ = reject(row)
    assert not rejected


def test_living_artist_with_birth_year() -> None:
    row = {
        "tags": ["techno"],
        "bio_snippet": "Artist (born 1980 in Amsterdam) has been active since 2005.",
    }
    rejected, _ = reject(row)
    assert not rejected


# --- Layer B: tag polarity (requires n_sets_for_artist) ---

def test_layer_b_rejects_recurring_booking_without_electronic_tag() -> None:
    """Julie — real wrong match: 6 De School sets, but tags are shoegaze/noise pop."""
    row = {
        "tags": ["shoegaze", "noise pop", "noise rock", "grunge", "pop"],
        "bio_snippet": "julie is an American shoegaze band from Los Angeles.",
    }
    rejected, reason = reject(row, n_sets_for_artist=6)
    assert rejected
    assert "tag polarity" in reason.lower()


def test_layer_b_ignores_single_booking() -> None:
    """n=1 means we lack the booking-pattern prior — skip the tag-polarity check."""
    row = {"tags": ["shoegaze", "noise pop", "noise rock"]}
    rejected, _ = reject(row, n_sets_for_artist=1)
    assert not rejected


def test_layer_b_ignores_thin_tag_data() -> None:
    """Fewer than 3 Last.fm tags = not enough signal. Don't fire."""
    row = {"tags": ["netherlands", "dj"]}
    rejected, _ = reject(row, n_sets_for_artist=5)
    assert not rejected


def test_layer_b_keeps_electronic_in_top_3() -> None:
    """Electronic marker anywhere in top-3 vouches for the dossier."""
    row = {"tags": ["netherlands", "dj", "techno", "amsterdam"]}
    rejected, _ = reject(row, n_sets_for_artist=5)
    assert not rejected


def test_layer_b_without_n_sets_kwarg_is_layer_a_only() -> None:
    """Backwards-compatible: no n_sets → only Layer A runs."""
    # Shoegaze tags (would trip Layer B if n_sets were passed); no blacklist hit.
    row = {"tags": ["shoegaze", "noise pop", "noise rock"]}
    rejected, _ = reject(row)
    assert not rejected


def test_layer_b_respects_electronic_positive_list() -> None:
    """A well-tagged cloud rap act (legitimate De School booking) stays."""
    row = {"tags": ["cloud rap", "hip-hop", "experimental"]}
    rejected, _ = reject(row, n_sets_for_artist=3)
    assert not rejected
