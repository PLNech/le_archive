"""Sliding-window audio consistency check.

For a sample of already-enriched sets, re-run librosa on three overlapping
windows (first third / middle third / last third) and check that bpm,
energy, brightness agree. If they don't, our single-pass `beat_track`
likely averaged across a tempo change and the stored number is misleading.

Useful as a spot-check; not something to run across all 891.

    poetry run python -m le_archive.tools.audit_audio --sample 5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from random import Random

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
RAW_PATH = ROOT / "scraper" / "data" / "raw_sets.json"

ANALYSIS_SR = 22050


def download(url: str, workdir: Path) -> Path | None:
    stem = workdir / "audio"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--quiet",
                "--no-progress",
                "--no-warnings",
                "--no-cache-dir",
                "-f",
                "bestaudio",
                "-o",
                f"{stem}.%(ext)s",
                "--print",
                "after_move:filepath",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip().split("\n")[-1]
    p = Path(line)
    return p if p.exists() else None


def analyse_window(y: np.ndarray, sr: int) -> dict[str, float]:
    tempo_raw, _ = librosa.beat.beat_track(y=y, sr=sr)
    arr = np.atleast_1d(np.asarray(tempo_raw, dtype=float))
    bpm = float(arr[0]) if arr.size and arr[0] > 0 else 0.0
    sc = librosa.feature.spectral_centroid(y=y, sr=sr)
    brightness = float(np.mean(sc) / (sr / 2)) if sc.size else 0.0
    rms = librosa.feature.rms(y=y)
    energy = float(np.mean(rms)) if rms.size else 0.0
    return {"bpm": bpm, "brightness": brightness, "energy": energy}


def spread_ok(vals: list[float], tol_rel: float = 0.25) -> bool:
    if not vals:
        return True
    avg = sum(vals) / len(vals)
    if avg == 0:
        return all(v == 0 for v in vals)
    spread = max(abs(v - avg) for v in vals) / abs(avg)
    return spread <= tol_rel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    pool = [
        r
        for r in records
        if (r.get("_enrichment") or {}).get("audio") and r.get("mixcloud_url")
    ]
    rng = Random(args.seed)
    sample = rng.sample(pool, min(args.sample, len(pool)))

    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for r in sample:
            print(f"\n--- {r['objectID']} ---")
            print(f"stored: bpm={r.get('bpm')}, brightness={r.get('brightness')}, energy={r.get('energy_mean')}")
            audio_path = download(r["mixcloud_url"], workdir)
            if not audio_path:
                print("  download failed, skipping")
                continue
            try:
                y, sr = librosa.load(
                    str(audio_path), sr=ANALYSIS_SR, mono=True
                )
            finally:
                audio_path.unlink(missing_ok=True)

            total = len(y)
            windows = [
                ("head", 0, total // 3),
                ("mid", total // 3, 2 * total // 3),
                ("tail", 2 * total // 3, total),
            ]
            windowed = {}
            for label, a, b in windows:
                segment = y[a:b]
                if len(segment) < sr * 30:
                    continue
                m = analyse_window(segment, sr)
                windowed[label] = m
                print(
                    f"  {label:5s} bpm={m['bpm']:6.1f}  bright={m['brightness']:.3f}  energy={m['energy']:.3f}"
                )

            stored = {
                "bpm": r.get("bpm") or 0,
                "brightness": r.get("brightness") or 0,
                "energy_mean": r.get("energy_mean") or 0,
            }
            bpms = [w["bpm"] for w in windowed.values()]
            brights = [w["brightness"] for w in windowed.values()]
            energies = [w["energy"] for w in windowed.values()]

            consistent = all(
                [spread_ok(bpms), spread_ok(brights), spread_ok(energies)]
            )
            print(f"  consistent-across-windows: {'YES' if consistent else 'NO'}")

            results.append(
                {
                    "objectID": r["objectID"],
                    "stored": stored,
                    "windows": windowed,
                    "consistent": consistent,
                }
            )

    inconsistent = [r for r in results if not r["consistent"]]
    print(f"\n=== audit done — {len(results)} analysed, {len(inconsistent)} inconsistent ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
