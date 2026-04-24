"""Render a viz_fingerprint dict → PNG bytes.

Layout:
- Y axis: frequency band (0..23), low freq at bottom
- X axis: time, earliest at left
- Colour: magnitude via a perceptual magma-like palette

Used by the multimodal mood pipeline to feed the LLM a compact spectrogram
alongside the text metadata blob.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np
from PIL import Image


_MAGMA_LUT: np.ndarray | None = None


def _build_magma_lut() -> np.ndarray:
    """Minimal magma-ish LUT — 256 entries of RGB uint8.

    Hand-rolled so we don't drag matplotlib in. Four anchor stops interpolated
    linearly: black -> purple -> orange -> pale yellow.
    """
    stops = np.array(
        [
            [0, 0, 0],
            [75, 15, 110],
            [225, 90, 60],
            [255, 245, 210],
        ],
        dtype=np.float32,
    )
    positions = np.array([0.0, 0.33, 0.72, 1.0], dtype=np.float32)
    xs = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    r = np.interp(xs, positions, stops[:, 0])
    g = np.interp(xs, positions, stops[:, 1])
    b = np.interp(xs, positions, stops[:, 2])
    return np.stack([r, g, b], axis=1).clip(0, 255).astype(np.uint8)


def _get_lut() -> np.ndarray:
    global _MAGMA_LUT
    if _MAGMA_LUT is None:
        _MAGMA_LUT = _build_magma_lut()
    return _MAGMA_LUT


def decode_fingerprint(fp: dict[str, Any]) -> np.ndarray:
    """Decode `viz_fingerprint` dict → (bands, n_frames) uint8 array.

    Raises ValueError on bad payload.
    """
    bands = int(fp.get("bands") or 0)
    b64 = fp.get("data_b64")
    if not bands or not b64:
        raise ValueError("fingerprint missing bands or data_b64")
    raw = base64.b64decode(b64)
    n_frames = len(raw) // bands
    if n_frames * bands != len(raw):
        raise ValueError(
            f"fingerprint size {len(raw)} not divisible by bands={bands}"
        )
    # File layout is time-major (frame, band); rearrange to (band, frame) for
    # a conventional spectrogram picture where low freq is at the bottom.
    u8_t = np.frombuffer(raw, dtype=np.uint8).reshape(n_frames, bands)
    return u8_t.T[::-1]  # flip so band 0 (low freq) lands at bottom row


def fingerprint_to_png(
    fp: dict[str, Any],
    target_width: int = 512,
    target_height: int = 96,
) -> bytes:
    """Render fingerprint to a compact PNG. Returns raw bytes.

    Resamples width with nearest-neighbour (preserves temporal edges) and
    upscales the 24-band axis to `target_height` with nearest-neighbour too.
    """
    grid = decode_fingerprint(fp)  # (bands, n_frames)
    lut = _get_lut()
    rgb = lut[grid]  # (bands, n_frames, 3)
    img = Image.fromarray(rgb, mode="RGB")
    img = img.resize((target_width, target_height), Image.Resampling.NEAREST)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def fingerprint_to_data_uri(fp: dict[str, Any], **kwargs: Any) -> str:
    """Convenience: PNG bytes → `data:image/png;base64,...` string."""
    png = fingerprint_to_png(fp, **kwargs)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
