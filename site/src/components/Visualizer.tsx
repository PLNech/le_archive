import { useEffect, useRef } from "react";
import type { FingerprintReader } from "../hooks/useFingerprint";

type Props = {
  playing: boolean;
  height?: number;
  bars?: number;
  /** When provided, real FFT from AnalyserNode drives the viz (highest priority). */
  getAnalyser?: () => AnalyserNode | null;
  /** Pre-computed spectral fingerprint; played back in sync with `fingerprintPosition`. */
  fingerprint?: FingerprintReader;
  /** Current playback position in seconds (for fingerprint lookup). */
  fingerprintPosition?: number;
};

/**
 * Monochromatic ink-on-paper bars.
 *
 * Priority of data sources (first available wins):
 * 1. Real FFT from AnalyserNode (tab-audio capture) — live truth.
 * 2. Precomputed fingerprint — honest spectra of THIS set, synced to position.
 * 3. Generative layered sines — cosmetic fallback when neither is available.
 */
export function Visualizer({
  playing,
  height = 36,
  bars = 32,
  getAnalyser,
  fingerprint,
  fingerprintPosition,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Mutable refs so the RAF loop reads fresh values without resubscribing
  const positionRef = useRef<number>(fingerprintPosition ?? 0);
  positionRef.current = fingerprintPosition ?? 0;
  const fingerprintRef = useRef<FingerprintReader | undefined>(fingerprint);
  fingerprintRef.current = fingerprint;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const state = {
      heights: new Array(bars).fill(0),
      peaks: new Array(bars).fill(0),
    };

    let raf = 0;
    let mounted = true;
    let freqBuf: Uint8Array | null = null;
    let binRanges: Array<[number, number]> | null = null;
    let fpBuf: Uint8Array | null = null;
    let fpMode: "none" | "ready" = "none";

    function ensureBinMap(analyser: AnalyserNode) {
      if (
        freqBuf &&
        freqBuf.length === analyser.frequencyBinCount &&
        binRanges &&
        binRanges.length === bars
      ) {
        return;
      }
      freqBuf = new Uint8Array(analyser.frequencyBinCount);
      const nyquist = analyser.context.sampleRate / 2;
      const minHz = 40;
      const maxHz = Math.min(16000, nyquist);
      const lnMin = Math.log(minHz);
      const lnMax = Math.log(maxHz);
      const total = analyser.frequencyBinCount;
      const ranges: Array<[number, number]> = [];
      for (let i = 0; i < bars; i++) {
        const a = Math.exp(lnMin + ((lnMax - lnMin) * i) / bars);
        const b = Math.exp(lnMin + ((lnMax - lnMin) * (i + 1)) / bars);
        const aBin = Math.max(0, Math.floor((a / nyquist) * total));
        const bBin = Math.min(total, Math.max(aBin + 1, Math.ceil((b / nyquist) * total)));
        ranges.push([aBin, bBin]);
      }
      binRanges = ranges;
    }

    function ensureFingerprintBuf(): boolean {
      const fp = fingerprintRef.current;
      if (!fp) {
        fpMode = "none";
        return false;
      }
      if (!fpBuf || fpBuf.length !== fp.bands) {
        fpBuf = new Uint8Array(fp.bands);
      }
      fpMode = "ready";
      return true;
    }

    function resize() {
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function color(): string {
      const v = getComputedStyle(canvas!).getPropertyValue("--viz-ink").trim();
      return v || "#1a1713";
    }

    function render(t: number) {
      if (!mounted || !canvas || !ctx) return;
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      const gap = 2;
      const barWidth = Math.max(1, (w - (bars - 1) * gap) / bars);
      const ink = color();

      const analyser = getAnalyser?.() ?? null;
      const realFFT = Boolean(analyser && playing);
      const fp = fingerprintRef.current;
      const useFP = !realFFT && playing && ensureFingerprintBuf() && fp;

      if (analyser) ensureBinMap(analyser);
      if (realFFT && analyser && freqBuf && binRanges) {
        analyser.getByteFrequencyData(freqBuf);
      }
      if (useFP && fp && fpBuf) {
        fp.readAt(positionRef.current, fpBuf);
      }

      for (let i = 0; i < bars; i++) {
        let target: number;
        if (realFFT && freqBuf && binRanges) {
          const [a, b] = binRanges[i];
          let sum = 0;
          let count = 0;
          for (let j = a; j < b; j++) {
            sum += freqBuf[j];
            count++;
          }
          const avg = count > 0 ? sum / count : 0;
          target = Math.pow(avg / 255, 1.3);
        } else if (useFP && fp && fpBuf) {
          // Interpolate fp.bands → viz bars (linear)
          const srcF = fp.bands <= 1 ? 0 : (i * (fp.bands - 1)) / (bars - 1);
          const lo = Math.floor(srcF);
          const hi = Math.min(fp.bands - 1, lo + 1);
          const frac = srcF - lo;
          const v = fpBuf[lo] * (1 - frac) + fpBuf[hi] * frac;
          target = Math.pow(v / 255, 1.2);
        } else if (playing) {
          const mid = 1 - Math.abs(i - bars / 2) / (bars / 2);
          const envelope = 0.35 + 0.55 * mid;
          target =
            envelope *
            (0.45 +
              0.25 * Math.sin(t * 0.0032 + i * 0.41) +
              0.18 * Math.sin(t * 0.0071 + i * 1.13) +
              0.12 * Math.sin(t * 0.0123 + i * 0.67));
          target = Math.max(0.04, Math.min(1, target));
        } else {
          target = 0;
        }

        const ease = realFFT ? 0.55 : useFP ? 0.35 : playing ? 0.22 : 0.12;
        state.heights[i] += (target - state.heights[i]) * ease;
        if (state.heights[i] > state.peaks[i]) {
          state.peaks[i] = state.heights[i];
        } else {
          const decay = realFFT ? 0.012 : useFP ? 0.01 : playing ? 0.008 : 0.02;
          state.peaks[i] = Math.max(0, state.peaks[i] - decay);
        }

        const x = i * (barWidth + gap);
        const barH = state.heights[i] * h;
        const peakY = h - state.peaks[i] * h;

        ctx.fillStyle = ink;
        ctx.globalAlpha = 0.82;
        ctx.fillRect(x, h - barH, barWidth, barH);

        if (state.peaks[i] > 0.02) {
          ctx.globalAlpha = 1;
          ctx.fillRect(x, Math.max(0, peakY - 1), barWidth, 1.5);
        }
      }

      ctx.globalAlpha = 0.35;
      ctx.fillStyle = ink;
      ctx.fillRect(0, h - 0.5, w, 0.5);

      // Discard unused dev-check
      void fpMode;

      raf = requestAnimationFrame(render);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    raf = requestAnimationFrame(render);

    return () => {
      mounted = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [playing, bars, getAnalyser]);

  return (
    <canvas
      ref={canvasRef}
      className="viz"
      style={{ height }}
      aria-hidden
    />
  );
}
