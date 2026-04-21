"""Polite HTTP client for hetarchief.deschoolamsterdam.nl.

- httpx + tenacity retries on 5xx
- 1s min-delay between requests (rate limit)
- Disk-cached responses under data/cache/ (keyed by URL sha1)
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

BASE = "https://hetarchief.deschoolamsterdam.nl"
USER_AGENT = (
    "Mozilla/5.0 (LeArchive research crawler; "
    "contact paullouis.nech@algolia.com)"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


CACHE_DIR = _repo_root() / "scraper" / "data" / "cache"


class ArchiveClient:
    def __init__(self, delay_s: float = 1.0, cache: bool = True) -> None:
        self.delay_s = delay_s
        self.cache = cache
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._last_request_at: float = 0.0
        self._client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "HX-Request": "true",  # needed for /embed/ fragments
            },
            follow_redirects=True,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ArchiveClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode()).hexdigest()
        return CACHE_DIR / f"{h}.html"

    def _sleep_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay_s:
            time.sleep(self.delay_s - elapsed)
        self._last_request_at = time.monotonic()

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError, httpx.ReadTimeout)
        ),
    )
    def _fetch_network(self, url: str) -> str:
        self._sleep_if_needed()
        r = self._client.get(url)
        if r.status_code >= 500:
            r.raise_for_status()
        return r.text

    def get(self, path_or_url: str) -> str:
        url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
        cp = self._cache_path(url)
        if self.cache and cp.exists():
            return cp.read_text(encoding="utf-8")
        text = self._fetch_network(url)
        if self.cache:
            cp.write_text(text, encoding="utf-8")
        return text
