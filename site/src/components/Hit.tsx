import type { SetRecord } from "../types";
import { usePlayerStore } from "../hooks/usePlayerStore";
import { useArtistModal } from "../hooks/useArtistModal";

type Props = { hit: SetRecord };

function fmtDuration(seconds?: number): string {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
}

export function Hit({ hit }: Props) {
  const play = usePlayerStore((s) => s.play);
  const openArtist = useArtistModal((s) => s.open);
  const canPlay = Boolean(hit.mixcloud_url);
  const duration = fmtDuration(hit.duration);

  return (
    <article className="hit">
      <div className="hit-cells">
        <div className="cell hit-artists">
          {hit.cover_url ? (
            <img className="hit-cover" src={hit.cover_url} alt="" loading="lazy" />
          ) : (
            <span className="hit-cover hit-cover-placeholder" aria-hidden />
          )}
          <span className="hit-artists-text">
            {hit.artists.length === 0
              ? "—"
              : hit.artists.map((a, i) => (
                  <span key={`${a}-${i}`}>
                    {i > 0 && <span className="artist-sep"> · </span>}
                    <button
                      type="button"
                      className="artist-link"
                      onClick={() => openArtist(a)}
                    >
                      {a}
                    </button>
                  </span>
                ))}
          </span>
        </div>
        <div className="cell">{hit.date}</div>
        <div className="cell">{hit.space}</div>
        <div className="cell">{hit.event}</div>
        <div className="cell">
          {duration && <span className="hit-duration">{duration}</span>}
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
                coverUrl: hit.cover_url,
                duration: hit.duration,
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
