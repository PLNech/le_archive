"""Shared Algolia client factory."""

from __future__ import annotations

import os
from pathlib import Path

from algoliasearch.search.client import SearchClientSync
from dotenv import load_dotenv

INDEX_NAME = "archive_sets"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_env() -> None:
    # override=True so repo .env wins over shell-exported ALGOLIA_* vars
    # (user's shell exports work-account keys which shadow project creds otherwise).
    load_dotenv(_repo_root() / ".env", override=True)


def client() -> SearchClientSync:
    load_env()
    app_id = os.environ["ALGOLIA_APP_ID"]
    api_key = os.environ["ALGOLIA_API_KEY"]
    return SearchClientSync(app_id, api_key)
