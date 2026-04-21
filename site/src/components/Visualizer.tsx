import { useEffect, useRef } from "react";

type Props = {
  playing: boolean;
  height?: number;
  bars?: number;
};

/**
 * Sleek monochromatic bars — archival ink-on-paper, not rainbow Winamp.
 *
 * Honest disclosure: Mixcloud's cross-origin iframe doesn't expose audio
 * data, so this is *generative* — smoothed noise + sines, freezes when
 * paused. The motion is tuned to feel like ink trembling on a gauge, not
 * to pretend to be a spectrum analyzer.
 */
export function Visualizer({ playing, height = 36, bars = 32 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      if (!canvas) return;
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

      for (let i = 0; i < bars; i++) {
        let target: number;
        if (playing) {
          // Smoothed layered sines, biased slightly higher in the center
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

        // Ease heights, peak-hold with slow decay
        state.heights[i] += (target - state.heights[i]) * (playing ? 0.22 : 0.12);
        if (state.heights[i] > state.peaks[i]) {
          state.peaks[i] = state.heights[i];
        } else {
          state.peaks[i] = Math.max(0, state.peaks[i] - (playing ? 0.008 : 0.02));
        }

        const x = i * (barWidth + gap);
        const barH = state.heights[i] * h;
        const peakY = h - state.peaks[i] * h;

        ctx.fillStyle = ink;
        ctx.globalAlpha = 0.82;
        ctx.fillRect(x, h - barH, barWidth, barH);

        // Peak cap (the Winamp tell, done with restraint)
        if (state.peaks[i] > 0.02) {
          ctx.globalAlpha = 1;
          ctx.fillRect(x, Math.max(0, peakY - 1), barWidth, 1.5);
        }
      }

      // Base rule — archival graph-paper hint
      ctx.globalAlpha = 0.35;
      ctx.fillStyle = ink;
      ctx.fillRect(0, h - 0.5, w, 0.5);

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
  }, [playing, bars]);

  return (
    <canvas
      ref={canvasRef}
      className="viz"
      style={{ height }}
      aria-hidden
    />
  );
}
