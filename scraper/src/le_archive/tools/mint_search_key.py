"""Mint a scoped, search-only Algolia API key for the public site.

The root .env holds the admin key (`ALGOLIA_API_KEY`) which must never leave
our machines. Vite inlines whatever is in `VITE_ALGOLIA_SEARCH_API_KEY` into
the JS bundle, so that value must be safe to put on a public CDN: ACL limited
to `search` + `browse`, indices restricted to `archive_*`.

This tool calls `add_api_key` on the admin client and prints the new key so
it can be pasted into `site/.env` (or dropped into a GitHub Actions secret).
Re-run to rotate; pass `--delete <key>` to revoke a previous one.

Usage:
    poetry run python -m le_archive.tools.mint_search_key
    poetry run python -m le_archive.tools.mint_search_key --delete <old_key>
"""

from __future__ import annotations

import argparse
import sys

from le_archive.algolia_client import client as make_client, load_env


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--delete", metavar="KEY", help="Revoke an existing key")
    p.add_argument(
        "--description",
        default="le_archive public site (search + browse, archive_*)",
    )
    args = p.parse_args()

    load_env()
    client = make_client()

    if args.delete:
        client.delete_api_key(key=args.delete)
        print(f"[mint] revoked key {args.delete[:6]}…")
        return 0

    resp = client.add_api_key(
        api_key={
            "acl": ["search", "listIndexes"],
            "indexes": [
                "archive_sets",
                "archive_sets_newest",
                "archive_sets_oldest",
                "archive_artists",
            ],
            "description": args.description,
        }
    )
    # SDK returns a response object with .key / .created_at etc.
    key = getattr(resp, "key", None) or resp["key"]
    print(f"[mint] created key: {key}")
    print(f"[mint] paste into site/.env as VITE_ALGOLIA_SEARCH_API_KEY=...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
