import { useEffect } from "react";
import { useArtistModal } from "../hooks/useArtistModal";
import { useArtistSummary } from "../hooks/useArtistSummary";
import { useArtistDossier } from "../hooks/useArtistDossier";
import { useArtistSets } from "../hooks/useArtistSets";
import { usePlayerStore } from "../hooks/usePlayerStore";
import { trackClick } from "../lib/insights";

function fmtDuration(seconds?: number): string {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
}

function formatCount(n?: number): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString("en-US");
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("");
}

export function ArtistModal() {
  const name = useArtistModal((s) => s.name);
  const open = useArtistModal((s) => s.open);
  const close = useArtistModal((s) => s.close);
  const wiki = useArtistSummary(name);
  const dossier = useArtistDossier(name);
  const artistSets = useArtistSets(name);
  const play = usePlayerStore((s) => s.play);

  useEffect(() => {
    if (!name) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [name, close]);

  if (!name) return null;

  const fallbackDiscogs = `https://www.discogs.com/search?q=${encodeURIComponent(
    name,
  )}&type=artist`;
  const fallbackMixcloud = `https://www.mixcloud.com/search/?q=${encodeURIComponent(
    name,
  )}`;

  const d = dossier.state === "found" ? dossier.dossier : null;
  const w = wiki.state === "found" ? wiki.summary : null;

  const plateImg = w?.thumbnail?.source;
  const intro = w?.description;
  const longform = w?.extract || d?.bio_snippet;
  const shortProfile = d?.profile;

  const genres = (d?.tags ?? []).slice(0, 8);
  const similar = (d?.similar ?? []).slice(0, 10);
  const stillLoading = dossier.state === "loading" || wiki.state === "loading";
  const nothingFound =
    dossier.state === "not-found" && wiki.state === "not-found" && !d && !w;

  return (
    <div
      className="artist-modal-backdrop"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label={`Dossier: ${name}`}
    >
      <aside className="artist-modal" onClick={(e) => e.stopPropagation()}>
        <div className="artist-modal-plate">
          {plateImg ? (
            <img
              className="artist-modal-plate-img"
              src={plateImg}
              alt={`${name} — portrait from Wikipedia`}
            />
          ) : (
            <div className="artist-modal-plate-fallback" aria-hidden>
              {initials(name) || "·"}
            </div>
          )}
          <span className="artist-modal-plate-caption">
            {plateImg ? "plate · from wikipedia" : "plate · no portrait on file"}
          </span>
        </div>

        <header className="artist-modal-head">
          <span className="artist-modal-eyebrow">Dossier</span>
          <h2 className="artist-modal-name">{name}</h2>
          {d && (d.listeners || d.playcount) && (
            <div className="artist-modal-stats">
              {d.listeners !== undefined && (
                <span title="Last.fm listeners">
                  <strong>{formatCount(d.listeners)}</strong> listeners
                </span>
              )}
              {d.playcount !== undefined && (
                <span title="Last.fm scrobbles">
                  <strong>{formatCount(d.playcount)}</strong> plays
                </span>
              )}
            </div>
          )}
          <button
            className="artist-modal-close"
            onClick={close}
            aria-label="close"
            type="button"
          >
            ✕
          </button>
        </header>

        <div className="artist-modal-body">
          {stillLoading && !d && !w && (
            <p className="artist-modal-status">reading the archive…</p>
          )}

          {intro && <p className="artist-modal-desc">{intro}</p>}
          {shortProfile && !intro && (
            <p className="artist-modal-desc">{shortProfile}</p>
          )}
          {longform && <p className="artist-modal-extract">{longform}</p>}

          {genres.length > 0 && (
            <div className="artist-modal-chips-block">
              <span className="artist-modal-chips-label">Canon</span>
              <div className="artist-modal-chips">
                {genres.map((g) => (
                  <span key={g} className="artist-modal-chip">
                    {g}
                  </span>
                ))}
              </div>
            </div>
          )}

          {similar.length > 0 && (
            <div className="artist-modal-chips-block">
              <span className="artist-modal-chips-label">Seminar peers</span>
              <div className="artist-modal-chips">
                {similar.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="artist-modal-chip artist-modal-chip--link"
                    onClick={() => open(s)}
                    title={`open dossier: ${s}`}
                  >
                    {s} ↗
                  </button>
                ))}
              </div>
            </div>
          )}

          {nothingFound && (
            <p className="artist-modal-status">
              no dossier on file. the archive keeps some faculty anonymous.
            </p>
          )}

          {artistSets.state === "ready" && artistSets.sets.length > 0 && (
            <div className="artist-modal-sessions">
              <div className="artist-modal-sessions-head">
                <span className="artist-modal-chips-label">
                  Sessions on file
                </span>
                <span className="artist-modal-sessions-count">
                  {artistSets.sets.length}
                </span>
              </div>
              <ul className="artist-modal-sessions-list">
                {artistSets.sets.map((s) => {
                  const playable = Boolean(s.mixcloud_url);
                  return (
                    <li key={s.objectID}>
                      <button
                        type="button"
                        className="artist-modal-session"
                        disabled={!playable}
                        onClick={() => {
                          if (!s.mixcloud_url) return;
                          trackClick(s.objectID, "Dossier Set Played");
                          play({
                            objectID: s.objectID,
                            artists: s.artists,
                            date: s.date,
                            space: s.space,
                            event: s.event,
                            mixcloudUrl: s.mixcloud_url,
                            coverUrl: s.cover_url,
                            duration: s.duration,
                            fingerprint: s.viz_fingerprint,
                            similarBySound: s.similar_by_sound,
                          });
                        }}
                        title={
                          playable
                            ? `play: ${s.date} · ${s.space} · ${s.event}`
                            : "no audio on file"
                        }
                      >
                        <span className="artist-modal-session-date">
                          {s.date}
                        </span>
                        <span className="artist-modal-session-body">
                          <span className="artist-modal-session-event">
                            {s.event || "—"}
                          </span>
                          <span className="artist-modal-session-space">
                            {s.space || "—"}
                          </span>
                        </span>
                        <span className="artist-modal-session-meta">
                          {s.duration ? fmtDuration(s.duration) : "—"}
                        </span>
                        <span
                          className="artist-modal-session-play"
                          aria-hidden
                        >
                          {playable ? "▸" : "·"}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        <footer className="artist-modal-foot">
          <span className="artist-modal-foot-label">cross-references</span>
          {w?.content_urls?.desktop?.page && (
            <a
              href={w.content_urls.desktop.page}
              target="_blank"
              rel="noreferrer"
            >
              Wikipedia ↗
            </a>
          )}
          <a
            href={d?.discogs_url || fallbackDiscogs}
            target="_blank"
            rel="noreferrer"
          >
            Discogs ↗
          </a>
          {d?.lastfm_url && (
            <a href={d.lastfm_url} target="_blank" rel="noreferrer">
              Last.fm ↗
            </a>
          )}
          <a href={fallbackMixcloud} target="_blank" rel="noreferrer">
            Mixcloud ↗
          </a>
        </footer>
      </aside>
    </div>
  );
}
