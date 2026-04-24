"""Idempotent Algolia index setup: searchable attrs, facets, ranking.

Run once at Phase 0 and any time settings change:

    poetry run python -m le_archive.setup_index
"""

from __future__ import annotations

from algoliasearch.search.config import SearchConfig

from le_archive.algolia_client import INDEX_NAME, client

ARTISTS_INDEX = "archive_artists"

SETTINGS = {
    "searchableAttributes": [
        "artists",
        "event",
        "space",
        "tags",
    ],
    "attributesForFaceting": [
        "searchable(artists)",
        "searchable(event)",
        "year",
        "space",
        "tags",
        "is_b2b",
        # Populated in later phases; safe to declare early.
        "searchable(artist_genres)",
        "mixcloud_tags",
        "searchable(mood)",
        "focus_score",
        "duration_bucket",
        "tempo_bucket",
        "energy",
        # P6 numeric audio features (range sliders)
        "bpm",
        "brightness",
        "noisiness",
        "energy_mean",
        "energy_dynamic_range",
        # Enrichment gates — declared facetable so the debug strip can filter on each.
        "_enrichment.audio",
        "_enrichment.mood",
        "_enrichment.artists",
        "_enrichment.mixcloud",
    ],
    "customRanking": [
        "desc(play_count)",
        "desc(date_ts)",
    ],
    "attributesToRetrieve": ["*"],
}


ARTIST_SETTINGS = {
    "searchableAttributes": ["name", "aliases", "tags", "similar"],
    "attributesForFaceting": [
        "searchable(tags)",
        "searchable(similar)",
    ],
    "customRanking": ["desc(listeners)", "desc(playcount)"],
    "attributesToRetrieve": ["*"],
}


def main() -> None:
    c = client()
    resp = c.set_settings(index_name=INDEX_NAME, index_settings=SETTINGS)
    print(f"Applied settings to index '{INDEX_NAME}' (taskID={resp.task_id}).")
    c.wait_for_task(index_name=INDEX_NAME, task_id=resp.task_id)

    resp2 = c.set_settings(index_name=ARTISTS_INDEX, index_settings=ARTIST_SETTINGS)
    print(
        f"Applied settings to index '{ARTISTS_INDEX}' (taskID={resp2.task_id})."
    )
    c.wait_for_task(index_name=ARTISTS_INDEX, task_id=resp2.task_id)
    print("Indices ready.")


if __name__ == "__main__":
    main()
