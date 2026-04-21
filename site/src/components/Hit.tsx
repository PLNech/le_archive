import type { SetRecord } from "../types";
import { usePlayerStore } from "../hooks/usePlayerStore";

type Props = { hit: SetRecord };

export function Hit({ hit }: Props) {
  const play = usePlayerStore((s) => s.play);
  const canPlay = Boolean(hit.mixcloud_url);

  return (
    <article className="hit">
      <div className="hit-cells">
        <div className="cell hit-artists">{hit.artists.join(" · ") || "—"}</div>
        <div className="cell">{hit.date}</div>
        <div className="cell">{hit.space}</div>
        <div className="cell">{hit.event}</div>
        <div className="cell">
          {hit.is_b2b && <span className="tag">b2b</span>}
          {hit.tags.map((t) => (
            <span className="tag" key={t}>
              {t}
            </span>
          ))}
        </div>
        <div className="cell hit-action">
          <button
            className="play-btn"
            disabled={!canPlay}
            onClick={() =>
              canPlay &&
              play({
                objectID: hit.objectID,
                artists: hit.artists,
                date: hit.date,
                space: hit.space,
                event: hit.event,
                mixcloudUrl: hit.mixcloud_url!,
              })
            }
          >
            {canPlay ? "play" : "—"}
          </button>
        </div>
      </div>
    </article>
  );
}
