import { useMemo } from "react";

export type FingerprintPayload = {
  bands: number;
  frame_seconds: number;
  n_frames: number;
  data_b64: string;
};

export type FingerprintReader = {
  bands: number;
  frameSeconds: number;
  nFrames: number;
  /** Fills `out` with the band values (0..255) for the frame covering `t` seconds. */
  readAt: (t: number, out: Uint8Array) => boolean;
};

function decodeBase64(s: string): Uint8Array {
  const bin = atob(s);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf;
}

export function useFingerprint(
  payload: FingerprintPayload | undefined,
): FingerprintReader | null {
  return useMemo(() => {
    if (!payload || !payload.data_b64) return null;
    const bytes = decodeBase64(payload.data_b64);
    const { bands, frame_seconds, n_frames } = payload;
    const expected = bands * n_frames;
    if (bytes.length < expected) return null;

    return {
      bands,
      frameSeconds: frame_seconds,
      nFrames: n_frames,
      readAt(t: number, out: Uint8Array): boolean {
        if (out.length < bands) return false;
        const idx = Math.max(
          0,
          Math.min(n_frames - 1, Math.floor(t / frame_seconds)),
        );
        const offset = idx * bands;
        for (let b = 0; b < bands; b++) out[b] = bytes[offset + b];
        return true;
      },
    };
  }, [payload]);
}
