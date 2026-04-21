import { useEffect, useRef, useState } from "react";
import { usePlayerStore } from "../hooks/usePlayerStore";
import { useAudioAnalyser } from "../hooks/useAudioAnalyser";
import { useFingerprint } from "../hooks/useFingerprint";
import { Visualizer } from "./Visualizer";

declare global {
  interface Window {
    Mixcloud?: {
      PlayerWidget: (iframe: HTMLIFrameElement) => MixcloudWidget;
    };
  }
}

type MixcloudEvent<T extends unknown[] = []> = {
  on: (cb: (...args: T) => void) => void;
};

type MixcloudWidget = {
  ready: Promise<void>;
  play: () => Promise<void>;
  pause: () => Promise<void>;
  togglePlay: () => Promise<void>;
  seek: (position: number) => Promise<boolean>;
  getPosition: () => Promise<number>;
  getDuration: () => Promise<number>;
  getIsPaused: () => Promise<boolean>;
  events: {
    play: MixcloudEvent;
    pause: MixcloudEvent;
    progress: MixcloudEvent<[number, number]>;
    ended: MixcloudEvent;
    error: MixcloudEvent<[Error]>;
  };
};

const WIDGET_API_SRC = "https://widget.mixcloud.com/media/js/widgetApi.js";

function widgetSrc(mixcloudUrl: string): string {
  const params = new URLSearchParams({
    hide_cover: "1",
    mini: "1",
    hide_artwork: "1",
    autoplay: "1",
    feed: mixcloudUrl,
  });
  return `https://player-widget.mixcloud.com/widget/iframe/?${params}`;
}

function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

function useMixcloudScript(): boolean {
  const [ready, setReady] = useState(() => Boolean(window.Mixcloud));
  useEffect(() => {
    if (window.Mixcloud) {
      setReady(true);
      return;
    }
    let existing = document.querySelector<HTMLScriptElement>(
      `script[src="${WIDGET_API_SRC}"]`
    );
    const onLoad = () => setReady(true);
    if (!existing) {
      existing = document.createElement("script");
      existing.src = WIDGET_API_SRC;
      existing.async = true;
      document.head.appendChild(existing);
    }
    existing.addEventListener("load", onLoad);
    return () => existing?.removeEventListener("load", onLoad);
  }, []);
  return ready;
}

export function Player() {
  const current = usePlayerStore((s) => s.current);
  const stop = usePlayerStore((s) => s.stop);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const widgetRef = useRef<MixcloudWidget | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(current?.duration ?? 0);
  const scriptReady = useMixcloudScript();
  const analyser = useAudioAnalyser();
  const fingerprint = useFingerprint(current?.fingerprint);

  useEffect(() => {
    if (!scriptReady || !iframeRef.current || !window.Mixcloud || !current) {
      return;
    }
    const widget = window.Mixcloud.PlayerWidget(iframeRef.current);
    widgetRef.current = widget;
    let mounted = true;

    widget.ready.then(async () => {
      if (!mounted) return;

      // Events only exist after ready resolves
      widget.events.play?.on(() => mounted && setPlaying(true));
      widget.events.pause?.on(() => mounted && setPlaying(false));
      widget.events.ended?.on(() => mounted && setPlaying(false));
      widget.events.progress?.on((pos, dur) => {
        if (!mounted) return;
        setPosition(pos);
        if (dur) setDuration(dur);
      });

      try {
        const d = await widget.getDuration();
        if (mounted && d) setDuration(d);
        const paused = await widget.getIsPaused();
        if (mounted) setPlaying(!paused);
      } catch {
        /* widget may not respond on first tick */
      }
    });

    return () => {
      mounted = false;
      widgetRef.current = null;
    };
  }, [scriptReady, current?.mixcloudUrl]);

  if (!current) return null;

  const pct = duration > 0 ? (position / duration) * 100 : 0;

  const toggle = async () => {
    const w = widgetRef.current;
    if (!w) return;
    try {
      await w.togglePlay();
    } catch {
      /* swallow */
    }
  };

  // Global space-to-toggle shortcut dispatches a CustomEvent we listen for.
  useEffect(() => {
    const onToggle = () => {
      widgetRef.current?.togglePlay().catch(() => { /* swallow */ });
    };
    window.addEventListener("player:toggle", onToggle);
    return () => window.removeEventListener("player:toggle", onToggle);
  }, []);

  const seekTo = async (e: React.MouseEvent<HTMLDivElement>) => {
    const w = widgetRef.current;
    if (!w || duration <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    try {
      await w.seek(Math.max(0, Math.min(1, ratio)) * duration);
    } catch {
      /* swallow */
    }
  };

  return (
    <div className="player" role="region" aria-label="audio player">
      <div className="player-head">
        {current.coverUrl && (
          <img className="player-cover" src={current.coverUrl} alt="" />
        )}
        <div className="player-titleblock">
          <span className={`player-now ${playing ? "" : "player-now--paused"}`}>
            {playing ? "in session" : "paused"}
          </span>
          <span className="player-artist">{current.artists.join(" · ")}</span>
        </div>
        <span className="player-meta">
          {current.date}
          <span className="dot">·</span>
          {current.space}
          <span className="dot">·</span>
          {current.event}
        </span>

        <button
          className="player-toggle"
          onClick={toggle}
          aria-label={playing ? "pause" : "play"}
          title={`${playing ? "pause" : "play"} · space`}
        >
          {playing ? "❙❙" : "▶"}
        </button>

        <button
          className="player-close"
          onClick={stop}
          aria-label="close player"
          title="close player · Esc"
        >
          ✕
        </button>
      </div>

      <div className="player-body">
        <div className="player-viz-wrap">
          <Visualizer
            playing={playing}
            height={40}
            bars={36}
            getAnalyser={analyser.active ? analyser.getAnalyser : undefined}
            fingerprint={fingerprint ?? undefined}
            fingerprintPosition={position}
          />
          <div className="player-viz-mode">
            {analyser.active
              ? "real FFT · tab audio"
              : fingerprint
                ? "fingerprint · pre-analyzed spectra"
                : "generative · no audio access"}
          </div>
        </div>

        <div className="player-scrubber" onClick={seekTo}>
          <div className="player-scrub-rail">
            <div
              className="player-scrub-fill"
              style={{ width: `${pct}%` }}
              aria-hidden
            />
          </div>
          <div className="player-scrub-times">
            <span>{fmtTime(position)}</span>
            <span className="muted">
              {duration > 0 ? fmtTime(duration) : "—"}
            </span>
          </div>
        </div>
      </div>

      <div className="player-volume-note">
        <span>
          {analyser.active ? (
            <>
              real FFT live —{" "}
              <button
                type="button"
                className="link-btn"
                onClick={analyser.stop}
              >
                stop audio sync
              </button>
            </>
          ) : analyser.supported ? (
            <>
              want real FFT?{" "}
              <button
                type="button"
                className="link-btn"
                onClick={analyser.requestSync}
                title="share this tab (with 'share audio' ticked) — we'll tap your own output stream for spectrum analysis"
              >
                sync tab audio
              </button>
              {analyser.error && (
                <span className="volume-err"> · {analyser.error}</span>
              )}
            </>
          ) : (
            <>tab-audio capture not supported in this browser</>
          )}
        </span>
        <span>
          volume lives in the browser tab — Mixcloud doesn't expose it.
        </span>
      </div>

      <div className="player-iframe-wrap" aria-hidden>
        <iframe
          ref={iframeRef}
          title={`Mixcloud — ${current.artists.join(" · ")}`}
          src={widgetSrc(current.mixcloudUrl)}
          frameBorder={0}
          allow="autoplay"
        />
      </div>
    </div>
  );
}
