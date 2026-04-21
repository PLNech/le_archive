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
    <div className="player">
      <div className="player-meta">
        <strong>{current.artists.join(" · ")}</strong>
        <span>
          {current.date} · {current.space} · {current.event}
        </span>
        <button className="player-close" onClick={stop} aria-label="close player">
          ×
        </button>
      </div>
      <iframe
        title="Mixcloud player"
        src={widgetSrc(current.mixcloudUrl)}
        width="100%"
        height="60"
        frameBorder={0}
        allow="autoplay"
      />
    </div>
  );
}
