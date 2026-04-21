"""Phase 6 — stream Mixcloud audio, analyze with librosa, delete, store features.

For each set with mixcloud_url and _enrichment.audio not set:
  1. yt-dlp → temp mp3 in /tmp/learchive-audio/{id}.mp3
  2. librosa.load → mono float32 at ANALYSIS_SR
  3. DELETE the temp file (stream-and-delete — no audio retained)
  4. Compute features (bpm, spectral, energy, fingerprint)
  5. Write to raw_sets.json + partial_update to Algolia

Resumable: honors `_enrichment.audio`. SIGINT-safe: finishes current set,
checkpoints, then stops. Default checkpoint cadence = every 5 sets.

Ethics: only derived numeric features are kept. No audio bytes are stored
beyond the transient temp file, which is deleted as soon as numpy has a
copy in RAM.

Usage:
    poetry run python -m le_archive.enrich_audio [--limit N] [--dry-run]
    poetry run python -m le_archive.enrich_audio --no-push  # file only
    poetry run python -m le_archive.enrich_audio --verbose
"""

from __future__ import annotations

import argparse
import base64
import gc
import json
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
from tqdm import tqdm

from le_archive.algolia_client import INDEX_NAME, client as make_client


RAW_PATH = Path(__file__).resolve().parents[3] / "scraper" / "data" / "raw_sets.json"
TMP_ROOT = Path(tempfile.gettempdir()) / "learchive-audio"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

ANALYSIS_SR = 22050
FINGERPRINT_BANDS = 24
FINGERPRINT_TARGET_FRAMES = 1800  # 24 × 1800 = 43.2 kB raw → ~58 kB base64
CHECKPOINT_EVERY = 5


def download(url: str, dst_stem: Path, timeout: int = 900) -> Path | None:
    """Download best audio via yt-dlp in the native codec (usually webm/opus).

    No transcoding — librosa+audioread+ffmpeg decode the native stream to
    float32 on load. Skipping the mp3 extract step saves minutes per set on
    long mixes; we discard the file after analysis anyway.

    Returns the produced path or None on failure.
    """
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-progress",
        "--no-warnings",
        "--no-cache-dir",
        "-f", "bestaudio",
        "-o", f"{dst_stem}.%(ext)s",
        "--print", "after_move:filepath",
        url,
    ]
    try:
        r = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    printed = (r.stdout or "").strip().splitlines()
    if printed:
        p = Path(printed[-1])
        if p.exists():
            return p
    # Fallback: find any file matching the stem
    for candidate in dst_stem.parent.iterdir():
        if candidate.name.startswith(dst_stem.name + "."):
            return candidate
    return None


def analyze(y: np.ndarray, sr: int) -> dict:
    """Compute all audio features from mono signal."""
    # --- Tempo / beat ------------------------------------------------------
    # librosa >=0.10 returns tempo as a length-1 ndarray (one BPM per segment,
    # default = one global). Coerce to scalar defensively.
    tempo_raw, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_arr = np.atleast_1d(np.asarray(tempo_raw, dtype=float))
    bpm = float(tempo_arr[0]) if tempo_arr.size and tempo_arr[0] > 0 else None

    # --- Spectral & energy -------------------------------------------------
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    rms = librosa.feature.rms(y=y)[0]

    nyquist = sr / 2
    brightness = float(centroid.mean() / nyquist)  # 0..1
    noisiness = float(flatness.mean())             # 0..1
    energy_mean = float(rms.mean())
    energy_std = float(rms.std())

    buckets = np.array_split(rms, 10)
    energy_curve = [float(b.mean()) for b in buckets]

    # --- Fingerprint -------------------------------------------------------
    # Compute mel at a fine hop (~186ms/frame) so every part of the signal is
    # covered, then aggregate into target frames by averaging. This is more
    # accurate than using a huge hop_length (which would sample only n_fft
    # samples out of each target frame's worth of audio).
    FINE_HOP = 4096
    S_fine = librosa.feature.melspectrogram(
        y=y, sr=sr, n_mels=FINGERPRINT_BANDS, hop_length=FINE_HOP, n_fft=FINE_HOP
    )  # shape: (bands, fine_frames)
    fine_frames = S_fine.shape[1]
    duration_s = len(y) / sr
    # Keep ≥2s per target frame; shrink frame count for short sets.
    target_frames = min(
        FINGERPRINT_TARGET_FRAMES, max(30, int(duration_s / 2))
    )
    target_frames = min(target_frames, fine_frames)
    edges = np.linspace(0, fine_frames, target_frames + 1, dtype=int)
    S_agg = np.zeros((FINGERPRINT_BANDS, target_frames), dtype=np.float32)
    for i in range(target_frames):
        a, b = edges[i], edges[i + 1]
        if b > a:
            S_agg[:, i] = S_fine[:, a:b].mean(axis=1)
    frame_seconds = duration_s / target_frames
    S_db = librosa.power_to_db(S_agg, ref=np.max)
    lo, hi = float(S_db.min()), float(S_db.max())
    rng = hi - lo if hi - lo > 1e-6 else 1.0
    u8 = np.clip(((S_db - lo) / rng) * 255, 0, 255).astype(np.uint8)
    u8_t = u8.T  # time-major: each frame = FINGERPRINT_BANDS consecutive bytes
    data_b64 = base64.b64encode(u8_t.tobytes()).decode("ascii")

    # --- Buckets -----------------------------------------------------------
    if bpm is None or bpm < 100:
        tempo_bucket = "slow"
    elif bpm < 130:
        tempo_bucket = "mid"
    else:
        tempo_bucket = "fast"

    return {
        "bpm": round(bpm, 2) if bpm is not None else None,
        "tempo_bucket": tempo_bucket,
        "brightness": round(brightness, 4),
        "noisiness": round(noisiness, 4),
        "energy_mean": round(energy_mean, 4),
        "energy_dynamic_range": round(energy_std, 4),
        "energy_curve": [round(v, 4) for v in energy_curve],
        "viz_fingerprint": {
            "bands": FINGERPRINT_BANDS,
            "frame_seconds": round(frame_seconds, 3),
            "n_frames": int(u8_t.shape[0]),
            "data_b64": data_b64,
        },
    }


def process_one(record: dict, verbose: bool = False) -> dict | None:
    object_id = record["objectID"]
    url = record.get("mixcloud_url")
    if not url:
        return None

    stem = TMP_ROOT / object_id
    audio_path: Path | None = None
    try:
        if verbose:
            tqdm.write(f"  [{object_id}] downloading…")
        audio_path = download(url, stem)
        if audio_path is None:
            tqdm.write(f"  [{object_id}] yt-dlp failed")
            return None

        size_mb = audio_path.stat().st_size / 1024 / 1024
        if verbose:
            tqdm.write(f"  [{object_id}] {size_mb:.1f} MB → librosa…")

        y, sr = librosa.load(str(audio_path), sr=ANALYSIS_SR, mono=True)
        audio_path.unlink()  # stream-and-delete — audio gone from disk
        audio_path = None

        if verbose:
            tqdm.write(f"  [{object_id}] analyzing {len(y) / sr:.0f}s")
        features = analyze(y, sr)
        del y
        gc.collect()
        return features
    except Exception as e:
        tqdm.write(f"  [{object_id}] FAIL: {type(e).__name__}: {e}")
        return None
    finally:
        if audio_path is not None and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass


_interrupt = False


def _on_sigint(*_):
    global _interrupt
    _interrupt = True
    print("\n[phase6] ctrl-C received — finishing current set, then stopping")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="analyze 1 set, print features, no save/push")
    p.add_argument("--no-push", action="store_true",
                   help="mutate raw_sets.json only, skip Algolia partial_update")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    signal.signal(signal.SIGINT, _on_sigint)

    records = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    todo = [
        r for r in records
        if r.get("mixcloud_url")
        and not r.get("_enrichment", {}).get("audio")
        and not r.get("mixcloud_missing")
    ]
    # Always process shortest-first so visible progress accrues fast and
    # long marathon sets run once we're confident the pipeline is stable.
    todo.sort(key=lambda r: r.get("duration") or 99_999)

    print(f"[phase6] {len(todo)} sets pending audio analysis (shortest first)")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[phase6] limit → {len(todo)}")
    if args.dry_run:
        todo = todo[:1]
        print(
            f"[phase6] dry-run: 1 set (shortest available, "
            f"~{todo[0].get('duration') or '?'}s), no save, no push"
        )

    algolia = None if (args.dry_run or args.no_push) else make_client()

    ok = failed = since_checkpoint = 0
    for r in tqdm(todo, desc="audio"):
        if _interrupt:
            break
        features = process_one(r, args.verbose)
        if features is None:
            failed += 1
            continue
        r.update(features)
        r.setdefault("_enrichment", {})["audio"] = True
        ok += 1
        since_checkpoint += 1

        if algolia is not None:
            try:
                algolia.partial_update_object(
                    index_name=INDEX_NAME,
                    object_id=r["objectID"],
                    attributes_to_update={**features, "_enrichment": r["_enrichment"]},
                )
            except Exception as e:
                tqdm.write(f"  [{r['objectID']}] algolia update failed: {e}")

        if not args.dry_run and since_checkpoint >= CHECKPOINT_EVERY:
            RAW_PATH.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            since_checkpoint = 0
            tqdm.write(f"  checkpoint: {ok} ok, {failed} failed")

    if not args.dry_run and since_checkpoint > 0:
        RAW_PATH.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"[phase6] done: {ok} ok, {failed} failed")

    if args.dry_run and ok:
        sample = todo[0]
        fp = sample.get("viz_fingerprint", {})
        preview = {
            "objectID": sample["objectID"],
            "bpm": sample.get("bpm"),
            "tempo_bucket": sample.get("tempo_bucket"),
            "brightness": sample.get("brightness"),
            "noisiness": sample.get("noisiness"),
            "energy_mean": sample.get("energy_mean"),
            "energy_dynamic_range": sample.get("energy_dynamic_range"),
            "energy_curve": sample.get("energy_curve"),
            "viz_fingerprint_info": {
                "bands": fp.get("bands"),
                "frame_seconds": fp.get("frame_seconds"),
                "n_frames": fp.get("n_frames"),
                "data_b64_bytes": len(fp.get("data_b64", "")),
            },
        }
        print(json.dumps(preview, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
