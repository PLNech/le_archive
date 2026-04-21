# LeArchive

A local SPA for navigating the [De School Amsterdam archive](https://hetarchief.deschoolamsterdam.nl) — ~896 DJ sets from 2016–2024 — with Algolia search, metadata enrichment, and (eventually) mood-based filtering for focus listening.

## Layout

```
scraper/   Python pipeline (scrape → enrich → push to Algolia)
site/      Vite + React + react-instantsearch SPA
```

## Quick start

```bash
# 1. configure
cp .env.example .env  # fill in Algolia creds

# 2. scraper (Phase 1 + 2)
cd scraper
poetry install
poetry run python -m le_archive.scrape
poetry run python -m le_archive.index

# 3. site (Phase 3+)
cd ../site
npm install
npm run dev
```

## Plan

See `/home/pln/.claude/plans/peppy-riding-sparrow.md` for the full build plan (phases 0–8).
