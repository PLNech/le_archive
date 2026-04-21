import { useEffect } from "react";
import { useArtistModal } from "../hooks/useArtistModal";
import { useArtistSummary } from "../hooks/useArtistSummary";

export function ArtistModal() {
  const name = useArtistModal((s) => s.name);
  const close = useArtistModal((s) => s.close);
  const status = useArtistSummary(name);

  useEffect(() => {
    if (!name) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [name, close]);

  if (!name) return null;

  const discogsUrl = `https://www.discogs.com/search?q=${encodeURIComponent(
    name,
  )}&type=artist`;
  const mixcloudUrl = `https://www.mixcloud.com/search/?q=${encodeURIComponent(
    name,
  )}`;

  return (
    <div
      className="artist-modal-backdrop"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label={`Dossier: ${name}`}
    >
      <aside className="artist-modal" onClick={(e) => e.stopPropagation()}>
        <header className="artist-modal-head">
          <span className="artist-modal-eyebrow">Dossier</span>
          <h2 className="artist-modal-name">{name}</h2>
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
          {status.state === "loading" && (
            <p className="artist-modal-status">reading the archive…</p>
          )}

          {status.state === "found" && (
            <>
              {status.summary.thumbnail && (
                <img
                  className="artist-modal-thumb"
                  src={status.summary.thumbnail.source}
                  alt=""
                />
              )}
              {status.summary.description && (
                <p className="artist-modal-desc">{status.summary.description}</p>
              )}
              <p className="artist-modal-extract">{status.summary.extract}</p>
              {status.summary.content_urls?.desktop?.page && (
                <a
                  className="artist-modal-link"
                  href={status.summary.content_urls.desktop.page}
                  target="_blank"
                  rel="noreferrer"
                >
                  read on wikipedia ↗
                </a>
              )}
            </>
          )}

          {status.state === "not-found" && (
            <p className="artist-modal-status">
              no dossier on file. the archive keeps some faculty anonymous.
            </p>
          )}
        </div>

        <footer className="artist-modal-foot">
          <span className="artist-modal-foot-label">cross-references</span>
          <a href={discogsUrl} target="_blank" rel="noreferrer">
            Discogs ↗
          </a>
          <a href={mixcloudUrl} target="_blank" rel="noreferrer">
            Mixcloud ↗
          </a>
        </footer>
      </aside>
    </div>
  );
}
