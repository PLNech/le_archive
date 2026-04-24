"""Measure disambiguation rules against the LLM-audit ground truth.

The 2026-04-24 `audit_artists.py` run produced verdicts for all 457
artists (`data/artist_audit.json`). This harness treats those verdicts
as ground truth and reports precision/recall for the current rules.
Run after touching `disambiguation.py` to know whether a change was a
net win, and where the remaining recall gap lives.

Reports:
  - Overall precision/recall on live dossiers
  - Per-layer breakdown (A blacklist, A lifespan, B tag-polarity)
  - Sample of remaining wrong-live (what Layer C would have to catch)
  - Sample of FPs (correctly-resolved dossiers the rules would drop)

Usage:
    poetry run python -m le_archive.tools.validate_disambig
    poetry run python -m le_archive.tools.validate_disambig --confidence 8
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from le_archive.disambiguation import reject as disambig_reject

ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"
ARTISTS_PATH = ROOT / "scraper" / "data" / "artists.json"
AUDIT_PATH = ROOT / "scraper" / "data" / "artist_audit.json"


def classify(reason: str) -> str:
    if "blacklist" in reason:
        return "A-blacklist"
    if "lifespan" in reason:
        return "A-lifespan"
    if "tag polarity" in reason:
        return "B-tag-polarity"
    return "other"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--confidence",
        type=int,
        default=7,
        help="min LLM confidence to count as ground truth (default 7).",
    )
    p.add_argument("--samples", type=int, default=10)
    args = p.parse_args()

    if not AUDIT_PATH.exists():
        print(f"[validate] no audit at {AUDIT_PATH} — run audit_artists first", file=sys.stderr)
        return 2

    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    artists = json.loads(ARTISTS_PATH.read_text(encoding="utf-8"))
    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))

    n_sets_per_artist: Counter[str] = Counter()
    for r in records:
        for a in r.get("artists") or []:
            n_sets_per_artist[a] += 1

    wrong = {
        n for n, v in audit.items()
        if v.get("verdict") == "likely_wrong"
        and (v.get("confidence") or 0) >= args.confidence
    }
    correct = {n for n, v in audit.items() if v.get("verdict") == "likely_correct"}
    uncertain = {n for n, v in audit.items() if v.get("verdict") == "uncertain"}

    # Evaluate every audited artist (including those already rejected, so the
    # measurement is independent of current cache state — it scores the RULES).
    tp: list[tuple[str, str]] = []
    fp: list[tuple[str, str]] = []
    fn: list[str] = []
    tn_count = 0
    layer_hits: Counter[str] = Counter()

    for name in wrong | correct | uncertain:
        row = artists.get(name, {})
        # Strip any existing rejection marker — we want to re-evaluate fresh
        # on the dossier data (tags/bio), not on the cached verdict.
        if row.get("_phase_a_rejected") or row.get("_cleared_by_audit"):
            # We don't have the original dossier data for cleared rows (it was
            # deleted in apply_audit/apply_disambig). Skip for the measurement.
            # These were already caught, so we don't double-count.
            continue
        rejected, reason = disambig_reject(
            row, n_sets_for_artist=n_sets_per_artist.get(name, 0)
        )
        if rejected:
            layer_hits[classify(reason)] += 1
            if name in wrong:
                tp.append((name, reason))
            elif name in correct:
                fp.append((name, reason))
            # uncertain: neither tp nor fp
        else:
            if name in wrong:
                fn.append(name)
            elif name in correct:
                tn_count += 1

    # Already-caught rows count as TP for the union (rules + prior sweeps).
    already_caught = [
        n for n in wrong
        if (artists.get(n, {}).get("_phase_a_rejected")
            or artists.get(n, {}).get("_cleared_by_audit"))
    ]
    # They were caught by SOME rule (phase_a OR audit). For measurement, we
    # attribute them via the stored rejection reason when available.
    for n in already_caught:
        reason = artists.get(n, {}).get("_rejection_reason") or "audit-cleared"
        tp.append((n, reason))
        layer_hits[classify(reason) if "audit-cleared" not in reason else "llm-audit"] += 1

    total_wrong = len(wrong)
    total_tp = len(tp)
    total_fp = len(fp)
    recall = total_tp / total_wrong if total_wrong else 0
    # Precision: how many caught rows are truly wrong (only meaningful on rules,
    # not on audit-cleared which is ground truth by construction).
    rule_tp = sum(1 for _, r in tp if "audit-cleared" not in r)
    precision = rule_tp / (rule_tp + total_fp) if (rule_tp + total_fp) else 0

    print(f"=== Disambiguation validation (audit confidence >= {args.confidence}) ===\n")
    print(f"Ground truth: {len(wrong)} wrong, {len(correct)} correct, {len(uncertain)} uncertain\n")
    print(f"Rules + prior sweeps TP (wrong caught):       {total_tp:3d} / {total_wrong}")
    print(f"Rules FP (correct caught):                    {total_fp:3d}")
    print(f"FN (wrong still live):                        {len(fn):3d}")
    print(f"TN (correct kept):                            {tn_count:3d}")
    print(f"\nRecall (wrong-caught / total-wrong):          {recall:.1%}")
    print(f"Rule precision (rule-TP / (rule-TP + FP)):    {precision:.1%}\n")

    print("Layer breakdown:")
    for layer, ct in layer_hits.most_common():
        print(f"  {layer:20} {ct}")

    if fp:
        print(f"\n--- FP samples (correct dossiers rules would drop, max {args.samples}) ---")
        for name, reason in fp[: args.samples]:
            print(f"  {name}: {reason}")

    if fn:
        print(f"\n--- FN samples (wrong dossiers still live, max {args.samples}) ---")
        for name in fn[: args.samples]:
            row = artists.get(name, {})
            hint = audit.get(name, {}).get("hint", "")
            nset = n_sets_per_artist.get(name, 0)
            tags = (row.get("tags") or [])[:3]
            print(f"  {name:25} n={nset:2} tags={tags} hint={hint[:60]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
