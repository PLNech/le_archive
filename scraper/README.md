# le-archive scraper

Python pipeline: scrape De School archive → enrich → push to Algolia.

```bash
poetry install
cp ../.env.example ../.env  # fill in Algolia creds
poetry run python -m le_archive.scrape
poetry run python -m le_archive.index
```

See `../README.md` and `/home/pln/.claude/plans/peppy-riding-sparrow.md` for the full plan.
