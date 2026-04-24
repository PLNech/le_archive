"""Shared I/O helpers for enrichment workers.

The main reason this module exists: atomic writes. All enrichers serialise
records to `raw_sets.json` periodically; a crash mid-write would leave a
half-written file that breaks every subsequent run. We write to a sibling
tempfile + `os.replace` — on POSIX, replace is atomic on the same
filesystem, so readers either see the old version or the new one, never
a torn intermediate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialise `payload` as pretty-printed JSON to `path` atomically.

    Writes to `<path>.tmp`, flushes, then `os.replace`s. Readers will
    always see either the previous complete file or the new complete file.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
