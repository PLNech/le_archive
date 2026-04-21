import { usePlayerStore } from "../hooks/usePlayerStore";

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

export function Player() {
  const current = usePlayerStore((s) => s.current);
  const stop = usePlayerStore((s) => s.stop);

  if (!current) return null;
  return (
    <div className="player" role="region" aria-label="audio player">
      <div className="player-head">
        <span className="player-now">now playing</span>
        <span className="player-artist">{current.artists.join(" · ")}</span>
        <span className="player-meta">
          {current.date}
          <span className="dot">·</span>
          {current.space}
          <span className="dot">·</span>
          {current.event}
        </span>
        <button
          className="player-close"
          onClick={stop}
          aria-label="close player"
          title="close player"
        >
          ✕
        </button>
      </div>
      <div className="player-iframe-wrap">
        <iframe
          title={`Mixcloud — ${current.artists.join(" · ")}`}
          src={widgetSrc(current.mixcloudUrl)}
          frameBorder={0}
          allow="autoplay"
        />
      </div>
    </div>
  );
}
