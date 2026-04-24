import {
  useEnrichmentCoverage,
  ALL_FLAGS,
  type EnrichmentFlag,
} from "../hooks/useEnrichmentCoverage";
import { useDebugStore } from "../hooks/useDebugStore";

const LABEL: Record<EnrichmentFlag, string> = {
  audio: "audio · bpm/energy",
  artists: "artists · discogs+lastfm",
  mood: "mood · llm (pending)",
  mixcloud: "mixcloud · duration/cover",
};

/**
 * Thin debug strip showing live enrichment coverage. Each chip toggles an
 * AND-filter so you can slice the catalog to `sets where all X flags are
 * populated` — handy while workers are backfilling and you want to QA
 * the data that's already there.
 */
export function DebugStrip() {
  const coverage = useEnrichmentCoverage();
  const active = useDebugStore((s) => s.activeFlags);
  const toggle = useDebugStore((s) => s.toggle);
  const clear = useDebugStore((s) => s.clear);

  if (!coverage) return null;

  return (
    <section className="debug-strip" aria-label="enrichment debug filter">
      <span className="plate-eyebrow">Plate IV · Enrichment ledger</span>
      <div className="debug-chips">
        {ALL_FLAGS.map((flag) => {
          const n = coverage[flag];
          const pct = coverage.total > 0 ? (n / coverage.total) * 100 : 0;
          const on = active.includes(flag);
          return (
            <button
              key={flag}
              type="button"
              className={`debug-chip ${on ? "debug-chip--on" : ""}`}
              onClick={() => toggle(flag)}
              aria-pressed={on}
              title={
                on
                  ? `remove filter: ${flag}`
                  : `filter to sets with ${flag} enrichment`
              }
            >
              <span className="debug-chip-label">{LABEL[flag]}</span>
              <span className="debug-chip-count">
                {n.toLocaleString("nl-NL")}
                <span className="debug-chip-pct">
                  {" "}· {pct.toFixed(1)}%
                </span>
              </span>
              <span
                className="debug-chip-bar"
                style={{ width: `${pct}%` }}
                aria-hidden
              />
            </button>
          );
        })}
        {active.length > 0 && (
          <button
            type="button"
            className="debug-clear"
            onClick={clear}
            title="clear debug filters"
          >
            clear
          </button>
        )}
      </div>
    </section>
  );
}
