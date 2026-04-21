"""Idempotent Algolia index setup: searchable attrs, facets, ranking.

Run once at Phase 0 and any time settings change:

    poetry run python -m le_archive.setup_index
"""

from __future__ import annotations

from algoliasearch.search.config import SearchConfig

from le_archive.algolia_client import INDEX_NAME, client


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
        "artist_genres",
        "mixcloud_tags",
        "mood",
        "focus_score",
        "duration_bucket",
        "tempo_bucket",
        # P6 numeric audio features (range sliders)
        "bpm",
        "brightness",
        "noisiness",
        "energy_mean",
        "energy_dynamic_range",
        # Enrichment gate (filter out sets not yet analyzed)
        "_enrichment.audio",
        "_enrichment.mood",
    ],
    "customRanking": [
        "desc(play_count)",
        "desc(date_ts)",
    ],
    "attributesToRetrieve": ["*"],
}


def main() -> None:
    c = client()
    resp = c.set_settings(index_name=INDEX_NAME, index_settings=SETTINGS)
    print(f"Applied settings to index '{INDEX_NAME}' (taskID={resp.task_id}).")
    c.wait_for_task(index_name=INDEX_NAME, task_id=resp.task_id)
    print("Index ready.")


if __name__ == "__main__":
    main()
