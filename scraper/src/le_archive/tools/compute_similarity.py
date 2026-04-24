"""Compute top-K sound-similarity neighbors from P6 fingerprints.

For each set with a `viz_fingerprint` (24-band × T mel spectrogram, base64
uint8), we:
  1. Decode + reshape to (T, 24) → downsample T to a fixed pool of 32
     buckets via mean pooling → flatten to a 32×24 = 768-dim vector.
  2. L2-normalize each vector.
  3. Build the full cosine-similarity matrix (N × N).
  4. For each set, write back `similar_by_sound: [objectID, ...]` (top-K
     non-self) via Algolia `partial_update_object`.

Usage:
    poetry run python -m le_archive.tools.compute_similarity [--k 10] [--dry-run]

Runs offline, idempotent (overwrites similar_by_sound on each run). No
heavy deps — pure NumPy. Expected runtime for 886 × 768: <10s cosine +
~15s Algolia writes.
"""

from __future__ import annotations

import argparse
import base64
import sys

import numpy as np

from le_archive.algolia_client import INDEX_NAME, client as make_client

POOL_BUCKETS = 32  # Downsample T to this many time slots for fixed-dim vectors.
N_BANDS = 24


def decode_fingerprint(fp: dict) -> np.ndarray | None:
    """Decode base64 fingerprint into shape (n_frames, 24) float32.

    Returns None if payload looks malformed.
    """
    try:
        data = base64.b64decode(fp["data_b64"])
    except Exception:
        return None
    n_frames = int(fp.get("n_frames") or 0)
    bands = int(fp.get("bands") or N_BANDS)
    if n_frames <= 0 or bands != N_BANDS:
        return None
    if len(data) != n_frames * bands:
        return None
    arr = np.frombuffer(data, dtype=np.uint8).reshape(n_frames, bands).astype(np.float32)
    return arr


def pool_to_fixed(arr: np.ndarray, buckets: int) -> np.ndarray:
    """Mean-pool time-axis down to `buckets` rows. arr is (T, 24)."""
    T = arr.shape[0]
    if T <= buckets:
        # Nearest-repeat upsample — rare for our 1800-frame cap.
        idx = np.linspace(0, T - 1, buckets).astype(int)
        return arr[idx]
    edges = np.linspace(0, T, buckets + 1, dtype=int)
    out = np.zeros((buckets, arr.shape[1]), dtype=np.float32)
    for i in range(buckets):
        a, b = edges[i], edges[i + 1]
        if b > a:
            out[i] = arr[a:b].mean(axis=0)
    return out


def fetch_all(client) -> list[dict]:
    """Pull every record with `_enrichment.audio:true` + their fingerprint."""
    hits: list[dict] = []
    page = 0
    while True:
        r = client.search_single_index(
            index_name=INDEX_NAME,
            search_params={
                "filters": "_enrichment.audio:true",
                "hitsPerPage": 100,
                "page": page,
                "attributesToRetrieve": [
                    "objectID", "viz_fingerprint",
                    "bpm", "brightness", "noisiness",
                    "energy_mean", "energy_dynamic_range",
                ],
            },
        )
        page_hits = r.to_dict()["hits"]
        if not page_hits:
            break
        hits.extend(page_hits)
        if len(page_hits) < 100:
            break
        page += 1
    return hits


# Scalar features pulled alongside the fingerprint. Each is rank-normalised
# across the corpus so no single dimension dominates the cosine.
SCALAR_KEYS = ("bpm", "brightness", "noisiness", "energy_mean", "energy_dynamic_range")


def rank_normalize(values: list[float]) -> np.ndarray:
    """Map each value to its fractional rank in [0, 1]. Robust to outliers."""
    arr = np.asarray(values, dtype=np.float64)
    order = arr.argsort()
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.linspace(0, 1, len(arr))
    return ranks


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=10, help="top-K neighbors per set")
    p.add_argument("--dry-run", action="store_true",
                   help="compute + print stats, no Algolia writes")
    p.add_argument("--limit", type=int, default=None,
                   help="cap number of records for quick eval")
    args = p.parse_args()

    c = make_client()
    print("[similarity] fetching fingerprints from Algolia…")
    hits = fetch_all(c)
    if args.limit:
        hits = hits[: args.limit]
    print(f"[similarity] fetched {len(hits)} records")

    ids: list[str] = []
    pooled_vecs: list[np.ndarray] = []
    scalar_rows: list[list[float]] = []
    skipped = 0
    for h in hits:
        fp = h.get("viz_fingerprint")
        if not fp:
            skipped += 1
            continue
        raw = decode_fingerprint(fp)
        if raw is None:
            skipped += 1
            continue
        pooled = pool_to_fixed(raw, POOL_BUCKETS).flatten()
        if np.allclose(pooled, pooled.mean()):
            skipped += 1  # degenerate constant vector
            continue
        pooled_vecs.append(pooled.astype(np.float32))
        scalar_rows.append([float(h.get(k) or 0.0) for k in SCALAR_KEYS])
        ids.append(h["objectID"])

    print(f"[similarity] {len(ids)} usable vectors (skipped {skipped} malformed/empty)")
    if len(ids) < 2:
        print("[similarity] too few to compute similarity, exiting")
        return 1

    # Fingerprint stack — subtract corpus mean so we keep only the distinctive
    # texture per set, not the "all dance music looks kind of similar" baseline.
    FP = np.vstack(pooled_vecs)
    FP = FP - FP.mean(axis=0, keepdims=True)
    # L2-normalise per row. Rows with essentially no signal drop out with inf.
    fp_norms = np.linalg.norm(FP, axis=1, keepdims=True)
    fp_norms[fp_norms < 1e-6] = 1.0
    FP = FP / fp_norms

    # Scalar features — each rank-normalised to [0,1] so units don't bias
    # similarity (BPM values dwarf brightness otherwise).
    scalar_cols = np.asarray(scalar_rows, dtype=np.float64)
    S = np.stack(
        [rank_normalize(scalar_cols[:, i]) for i in range(scalar_cols.shape[1])],
        axis=1,
    ).astype(np.float32)
    # Centre + normalize the scalar block too.
    S = S - S.mean(axis=0, keepdims=True)
    s_norms = np.linalg.norm(S, axis=1, keepdims=True)
    s_norms[s_norms < 1e-6] = 1.0
    S = S / s_norms

    # Combine: 0.6 weight to fingerprint texture, 0.4 to scalar descriptors.
    # Weights are pre-baked into the concatenated unit-normed vector so a
    # single cosine does the right thing.
    FP_W, S_W = 0.6, 0.4
    V = np.hstack([FP * FP_W, S * S_W]).astype(np.float32)
    # Re-normalise so cosine == dot product.
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    print(
        f"[similarity] vector dim = fp({FP.shape[1]}) + scalar({S.shape[1]}) "
        f"= {V.shape[1]}"
    )
    print(f"[similarity] computing cosine ({V.shape[0]}×{V.shape[0]})…")
    sim = V @ V.T  # (N, N), already L2-normed rows
    np.fill_diagonal(sim, -np.inf)  # exclude self from nearest-neighbor
    k = min(args.k, len(ids) - 1)
    top_idx = np.argpartition(-sim, kth=k - 1, axis=1)[:, :k]
    # Sort those K by actual score descending.
    top_scores = np.take_along_axis(sim, top_idx, axis=1)
    order = np.argsort(-top_scores, axis=1)
    top_idx = np.take_along_axis(top_idx, order, axis=1)
    top_scores = np.take_along_axis(top_scores, order, axis=1)

    # Sanity sample: print the 3 nearest for the first few sets.
    print("[similarity] sanity sample:")
    for i in range(min(5, len(ids))):
        peers = [(ids[top_idx[i, j]], float(top_scores[i, j])) for j in range(min(k, 3))]
        peers_s = ", ".join(f"{pid[:36]}({sc:.2f})" for pid, sc in peers)
        print(f"  {ids[i][:48]:<48} → {peers_s}")

    if args.dry_run:
        print("[similarity] dry-run, no writes")
        return 0

    print(f"[similarity] writing similar_by_sound (top-{k}) back to {len(ids)} records…")
    ok = fail = 0
    for i, oid in enumerate(ids):
        peers = [ids[top_idx[i, j]] for j in range(k)]
        try:
            c.partial_update_object(
                index_name=INDEX_NAME,
                object_id=oid,
                attributes_to_update={"similar_by_sound": peers},
            )
            ok += 1
        except Exception as e:
            print(f"  fail {oid}: {e}", file=sys.stderr)
            fail += 1
    print(f"[similarity] done: {ok} updated, {fail} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
