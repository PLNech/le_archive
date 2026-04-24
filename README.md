# le_archive

A fan-built archive browser for [hetarchief.deschoolamsterdam.nl](https://hetarchief.deschoolamsterdam.nl) — ~891 DJ sets recorded at De School Amsterdam, 2016–2024, searchable + listenable in one place.

**Live:** [plnech.github.io/le_archive](https://plnech.github.io/le_archive/)

## What it is

De School's own archive is beautiful but hard to navigate: no search, no genre tags, no way to filter by mood or energy. This project scrapes the archive, enriches each set with metadata (Mixcloud stats, artist genres via Discogs + Last.fm, LLM-derived mood, librosa-derived tempo/brightness/energy), and serves it through a fast Algolia-backed SPA designed for one use case: **listening through the archive while working**.

No peak-time intrusions. Ambient and dub and atmospheric gems surfaced.

## Stack

```
scraper/   Python (Poetry) — scrape, Mixcloud/Discogs/Last.fm enrichment,
           LLM mood tagging, librosa audio analysis, Algolia push
site/      Vite + React 19 + TS + react-instantsearch + Zustand
```

- **Search:** Algolia (`archive_sets` + per-artist dossier index `archive_artists`)
- **Audio:** Mixcloud iframes — streamed in-browser, never re-hosted
- **Audio analysis:** librosa on `yt-dlp` streams, only derived numerical features stored (bpm, spectral centroid, energy envelope, viz fingerprint)
- **Mood tagging:** small LLM over artist + event + tags + audio features; closed 20-label vocabulary
- **Discovery:** cosine similarity over pooled mel fingerprints → hand-rolled "kin by sound"

## Running locally

```bash
cp .env.example .env                         # paste Algolia creds
cd scraper && poetry install
poetry run python -m le_archive.scrape       # (or skip + use existing index)
poetry run python -m le_archive.index

cd ../site && npm install && npm run dev     # http://localhost:5173
```

See `CLAUDE.md` for project conventions (lint gates, hook rules, P6 sharding, Mixcloud rate-limit gotchas).

## Credits

The archive itself is curated by **De School Amsterdam** at [hetarchief.deschoolamsterdam.nl](https://hetarchief.deschoolamsterdam.nl). Audio streams from **Mixcloud**. This project stores only derived numerical features (tempo, brightness, mood labels) — never the audio. Non-commercial fan tribute, unaffiliated with De School.

If De School or any featured artist objects, the derived features come down and we retreat to pure metadata. Just ask.
