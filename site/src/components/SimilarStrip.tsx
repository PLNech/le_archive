import { usePlayerStore } from "../hooks/usePlayerStore";
import { useSimilarSets } from "../hooks/useSimilarSets";
import { trackClick } from "../lib/insights";

const MAX = 6;

function fmtDuration(seconds?: number): string {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
}

/**
 * Ribbon under the Player showing up-to-MAX similar sets by sound — the
 * precomputed cosine-nearest neighbours from viz_fingerprint + scalar
 * features. Clicking one routes the Player to that set.
 *
 * Renders nothing if the current set has no neighbours yet (short track,
 * or fingerprint not computed).
 */
export function SimilarStrip() {
  const current = usePlayerStore((s) => s.current);
  const play = usePlayerStore((s) => s.play);
  const state = useSimilarSets(current?.similarBySound?.slice(0, MAX));

  if (!current || state.state === "idle") return null;
  if (state.state === "loading") {
    return (
      <div className="similar-strip similar-strip--muted">
        <span className="similar-strip-label">kin by sound</span>
        <span className="similar-strip-status">loading…</span>
      </div>
    );
  }
  if (state.state === "error" || state.sets.length === 0) return null;

  return (
    <div className="similar-strip">
      <span className="similar-strip-label">kin by sound</span>
      <div className="similar-strip-chips">
        {state.sets.map((s) => (
          <button
            key={s.objectID}
            type="button"
            className="similar-chip"
            onClick={() => {
              if (!s.mixcloud_url) return;
              trackClick(s.objectID, "Similar Set Played");
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
            title={`${s.date} · ${s.space} · ${s.event}${s.duration ? ` · ${fmtDuration(s.duration)}` : ""}`}
            disabled={!s.mixcloud_url}
          >
            <span className="similar-chip-artist">
              {s.artists.join(" · ") || "—"}
            </span>
            <span className="similar-chip-meta">{s.date}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
