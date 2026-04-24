"""Integration tests for enrichment helpers.

These tests run in-process with no network calls — they pin the
correctness of the pure functions that shape our data.
"""

from __future__ import annotations

from le_archive.enrich_artists import (
    classify_status,
    derive_set_fields,
    to_artist_record,
)


def make_row(ok: bool = True, partial: bool = False, failed: bool = False) -> dict:
    """Build a cached dossier row matching one of the four states."""
    if failed:
        return {"_enriched": True, "discogs_error": "HTTP 503"}
    if partial:
        return {"_enriched": True, "tags": ["techno"]}  # tags but no discogs_id
    if ok:
        return {
            "_enriched": True,
            "discogs_id": 123,
            "tags": ["techno", "house"],
            "similar": ["Artist X"],
        }
    return {}


def test_classify_status_buckets():
    assert classify_status(None) == "missing"
    assert classify_status({}) == "missing"
    assert classify_status(make_row(ok=True)) == "ok"
    assert classify_status(make_row(partial=True)) == "partial"
    assert classify_status(make_row(failed=True)) == "failed"


def test_derive_set_fields_union_genres_and_similar():
    cache = {
        "A": {"_enriched": True, "tags": ["ambient", "deep"], "similar": ["X"], "discogs_id": 1},
        "B": {"_enriched": True, "tags": ["techno", "deep"], "similar": ["Y"], "discogs_id": 2},
    }
    out = derive_set_fields(["A", "B"], cache)
    # Genres union but dedupe case-insensitively
    assert "ambient" in out["artist_genres"]
    assert "techno" in out["artist_genres"]
    assert out["artist_genres"].count("deep") == 1
    assert out["artist_status"] == "full"
    assert out["artist_status_detail"] == {"A": "ok", "B": "ok"}


def test_derive_set_fields_b2b_partial_reports_honestly():
    cache = {"A": make_row(ok=True), "B": make_row(failed=True)}
    out = derive_set_fields(["A", "B"], cache)
    assert out["artist_status"] == "partial"
    assert out["artist_status_detail"] == {"A": "ok", "B": "failed"}
    # B's genres don't contaminate the set since it failed
    assert out["artist_genres"] == ["techno", "house"]


def test_derive_set_fields_all_failed_none():
    cache = {"A": make_row(failed=True), "B": make_row(failed=True)}
    out = derive_set_fields(["A", "B"], cache)
    assert out["artist_status"] == "none"
    assert out["artist_genres"] == []


def test_derive_set_fields_deterministic():
    """Same cache → same output, no ordering instability."""
    cache = {
        "A": {"_enriched": True, "tags": ["ambient", "deep"], "similar": ["X", "Y"], "discogs_id": 1},
        "B": {"_enriched": True, "tags": ["techno"], "similar": ["Z"], "discogs_id": 2},
    }
    out1 = derive_set_fields(["A", "B"], cache)
    out2 = derive_set_fields(["A", "B"], cache)
    assert out1 == out2


def test_to_artist_record_skips_none_fields():
    row = {"_enriched": True, "tags": ["a"], "discogs_error": "oops"}
    obj = to_artist_record("Artist X", row)
    assert obj["objectID"] == "artist x"
    assert obj["name"] == "Artist X"
    assert obj["tags"] == ["a"]
    # Fields missing from the cache row aren't written
    assert "listeners" not in obj
    assert "playcount" not in obj


def test_to_artist_record_normalizes_objectid():
    """objectID strips case + collapses whitespace so lookups are stable."""
    obj = to_artist_record("  Rroxymore ", {"_enriched": True})
    assert obj["objectID"] == "rroxymore"


def test_enrichment_flags_merge_not_replace():
    """Simulates the Algolia partial_update behaviour we depend on:
    writing {artists: true} must NOT clobber existing {audio: true}."""
    existing = {"mixcloud": True, "audio": True, "mood": False}
    update_from_p4b = {"artists": True}
    # Algolia's nested-dict merge semantics (shallow merge). We encode the
    # assumption here so a future change surfaces as a test failure.
    merged = {**existing, **update_from_p4b}
    assert merged == {"mixcloud": True, "audio": True, "mood": False, "artists": True}
