"""Phase 1 — crawl the De School archive, produce data/raw_sets.json.

Usage:
    poetry run python -m le_archive.scrape [--dry-run] [--max-pages N] [--no-embed]

--dry-run      Fetch 1 index page + 3 embeds, print samples, write nothing.
--max-pages N  Limit page count (default: walk until empty).
--no-embed     Skip /embed/ fetches (scaffolding mode, Mixcloud URLs will be null).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from selectolax.parser import HTMLParser
from tqdm import tqdm

from le_archive.archive_client import BASE, ArchiveClient


OUT_PATH = Path(__file__).resolve().parents[3] / "scraper" / "data" / "raw_sets.json"

# Matches the mixcloud URL inside the iframe src inside the /embed/ fragment.
MIXCLOUD_URL_RE = re.compile(
    r"feed=(https?://www\.mixcloud\.com/[^\"&]+)", re.I
)
COMMENT_COUNT_RE = re.compile(r"(\d+)\s*comment", re.I)


@dataclass
class Set:
    objectID: str
    slug: str
    artists: list[str]
    date: str  # YYYY-MM-DD
    date_ts: int
    year: int
    weekday: str  # e.g. "saturday"
    space: str
    event: str
    tags: list[str]
    is_b2b: bool
    comment_count: int
    detail_url: str
    mixcloud_url: str | None
    _enrichment: dict = field(
        default_factory=lambda: {
            "mixcloud": False,
            "artists": False,
            "mood": False,
            "audio": False,
        }
    )


def _parse_date(dd_mm_yyyy: str) -> tuple[str, int, int]:
    d = dt.datetime.strptime(dd_mm_yyyy, "%d-%m-%Y").replace(tzinfo=dt.timezone.utc)
    return d.date().isoformat(), int(d.timestamp()), d.year


def _cell_texts(anchor) -> list[str]:
    """Return the 6 direct child-div text cells of a set anchor."""
    out: list[str] = []
    for child in anchor.iter(include_text=False):
        if child.tag == "div":
            out.append((child.text() or "").strip())
    return out


def parse_index_page(html: str) -> list[dict]:
    """Parse one /index/pageN into list of base-metadata dicts.

    Schema: slug, artist_raw, date_raw, space, event, tags_raw, comments_raw.
    """
    tree = HTMLParser(html)
    rows: list[dict] = []
    for a in tree.css("a[href*='/sets/']"):
        href = a.attributes.get("href") or ""
        # filter out nav/meta links
        slug_match = re.match(r"^/sets/([^/]+)/?$", href)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        cells = _cell_texts(a)
        if len(cells) < 5:
            continue
        # cells: [artist, date, space, event, tags?, comments?]
        # the 5th/6th are optional / often empty
        artist_raw = cells[0] if len(cells) > 0 else ""
        date_raw = cells[1] if len(cells) > 1 else ""
        space = cells[2] if len(cells) > 2 else ""
        event = cells[3] if len(cells) > 3 else ""
        tags_raw = cells[4] if len(cells) > 4 else ""
        comments_raw = cells[5] if len(cells) > 5 else ""
        rows.append(
            {
                "slug": slug,
                "artist_raw": artist_raw,
                "date_raw": date_raw,
                "space": space,
                "event": event,
                "tags_raw": tags_raw,
                "comments_raw": comments_raw,
            }
        )
    return rows


def parse_artists(raw: str) -> tuple[list[str], bool]:
    """Split artist field on ',' or '&'. Detect B2B (two+ artists)."""
    raw = raw.strip()
    if not raw:
        return [], False
    parts = [p.strip() for p in re.split(r"[,&]| b2b | with ", raw, flags=re.I) if p.strip()]
    return parts, len(parts) >= 2


def parse_tags(raw: str) -> list[str]:
    raw = raw.strip().lower()
    if not raw:
        return []
    return [t.strip() for t in re.split(r"[,/]", raw) if t.strip()]


def parse_comments(raw: str) -> int:
    m = COMMENT_COUNT_RE.search(raw or "")
    return int(m.group(1)) if m else 0


def parse_weekday_and_event_from_slug(slug: str) -> tuple[str, str]:
    """Extract weekday from the slug.

    Slug form: {DD-MM-YYYY}_{weekday}_{event}_{artist(s)}_{space}
    Return (weekday, event_slug). Event from slug can disambiguate when
    index column is wrong, but we generally trust the index column.
    """
    parts = slug.split("_")
    weekday = parts[1] if len(parts) > 1 else ""
    event_slug = parts[2] if len(parts) > 2 else ""
    return weekday, event_slug


def extract_mixcloud_url(embed_html: str) -> str | None:
    """Find the first mixcloud.com URL in the /embed/ fragment, skipping the
    commented-out placeholder feed."""
    # strip HTML comments to avoid the test placeholder
    no_comments = re.sub(r"<!--.*?-->", "", embed_html, flags=re.S)
    m = MIXCLOUD_URL_RE.search(no_comments)
    return m.group(1) if m else None


def build_set(row: dict, mixcloud_url: str | None) -> Set:
    artists, is_b2b = parse_artists(row["artist_raw"])
    date_iso, date_ts, year = _parse_date(row["date_raw"])
    weekday, _ = parse_weekday_and_event_from_slug(row["slug"])
    return Set(
        objectID=row["slug"],
        slug=row["slug"],
        artists=artists,
        date=date_iso,
        date_ts=date_ts,
        year=year,
        weekday=weekday,
        space=row["space"],
        event=row["event"],
        tags=parse_tags(row["tags_raw"]),
        is_b2b=is_b2b or "b2b" in (row["tags_raw"] or "").lower(),
        comment_count=parse_comments(row["comments_raw"]),
        detail_url=f"{BASE}/sets/{row['slug']}/",
        mixcloud_url=mixcloud_url,
        _enrichment={
            "mixcloud": mixcloud_url is not None,
            "artists": False,
            "mood": False,
            "audio": False,
        },
    )


def walk_pages(client: ArchiveClient, max_pages: int | None) -> Iterable[dict]:
    """Yield index rows, walking /index/page{N} until empty."""
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            return
        html = client.get(f"/index/page{page}")
        rows = parse_index_page(html)
        if not rows:
            return
        for r in rows:
            yield r
        page += 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--no-embed", action="store_true")
    args = p.parse_args()

    with ArchiveClient() as client:
        if args.dry_run:
            html = client.get("/index/page1")
            rows = parse_index_page(html)
            print(f"[dry-run] index page1 → {len(rows)} rows")
            for row in rows[:5]:
                mx = None
                if not args.no_embed:
                    emb = client.get(f"/sets/{row['slug']}/embed/")
                    mx = extract_mixcloud_url(emb)
                s = build_set(row, mx)
                print(json.dumps(asdict(s), ensure_ascii=False, indent=2))
            return 0

        # Full crawl
        rows = list(tqdm(walk_pages(client, args.max_pages), desc="index pages"))
        print(f"[phase1] collected {len(rows)} rows from index")

        # Dedup by slug (index may show same set across overlapping pages)
        by_slug: dict[str, dict] = {}
        for r in rows:
            by_slug.setdefault(r["slug"], r)
        print(f"[phase1] {len(by_slug)} unique slugs")

        records: list[dict] = []
        iterable = tqdm(by_slug.values(), desc="embed fetches")
        for r in iterable:
            mx = None
            if not args.no_embed:
                try:
                    emb = client.get(f"/sets/{r['slug']}/embed/")
                    mx = extract_mixcloud_url(emb)
                except Exception as e:
                    iterable.write(f"  embed fail for {r['slug']}: {e}")
            records.append(asdict(build_set(r, mx)))

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[phase1] wrote {len(records)} records → {OUT_PATH}")
        with_mx = sum(1 for r in records if r["mixcloud_url"])
        print(f"[phase1] with mixcloud url: {with_mx} / {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
