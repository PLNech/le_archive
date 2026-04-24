import { useFocusStore } from "../hooks/useFocusStore";
import type { TempoSelection } from "../hooks/useFocusStore";
import { useAudioCoverage } from "../hooks/useAudioCoverage";

const TEMPO_OPTIONS: { value: TempoSelection; label: string; sub: string }[] = [
  { value: "any", label: "all", sub: "any tempo" },
  { value: "slow", label: "slow", sub: "< 100 bpm" },
  { value: "mid", label: "mid", sub: "100–130" },
  { value: "fast", label: "fast", sub: "> 130" },
];

/**
 * Focus Strip — the seminar-room console.
 *
 * "Focus Now" one-click preset filters to low-energy / ambient territory.
 * Tempo chips let you narrow the pulse. Both filters rely on P6 audio
 * enrichment; sets without it are silently excluded from the filter
 * results (Algolia numeric filters ignore missing attributes).
 */
export function FocusStrip() {
  const focusNow = useFocusStore((s) => s.focusNow);
  const tempo = useFocusStore((s) => s.tempo);
  const toggleFocus = useFocusStore((s) => s.toggleFocus);
  const setTempo = useFocusStore((s) => s.setTempo);
  const reset = useFocusStore((s) => s.reset);
  const anyActive = focusNow || tempo !== "any";
  const coverage = useAudioCoverage();
  const coveragePct =
    coverage && coverage.total > 0
      ? Math.round((coverage.analyzed / coverage.total) * 100)
      : 0;

  return (
    <section className="focus-strip" aria-label="focus-mode filters">
      <div className="focus-strip-head">
        <span className="plate-eyebrow">Plate III · Focus Console</span>
        <span className="focus-strip-title">Seminar console</span>
        {coverage && (
          <span className="focus-coverage" title="sets with P6 audio features">
            <span className="focus-coverage-bar" aria-hidden>
              <span
                className="focus-coverage-fill"
                style={{ width: `${coveragePct}%` }}
              />
            </span>
            <span className="focus-coverage-label">
              {coverage.analyzed.toLocaleString("nl-NL")} /{" "}
              {coverage.total.toLocaleString("nl-NL")} analyzed
            </span>
          </span>
        )}
        <span className="focus-strip-hint">
          <span className="facet-hint-mech">AUDIO-DERIVED · EXCLUDES UN-ANALYZED</span>
        </span>
      </div>

      <div className="focus-strip-body">
        <button
          type="button"
          className={`focus-now ${focusNow ? "focus-now--on" : ""}`}
          onClick={toggleFocus}
          aria-pressed={focusNow}
          title="energy_mean ≤ 0.18 — roughly ambient / low-energy"
        >
          <span className="focus-now-dot" aria-hidden>●</span>
          <span className="focus-now-body">
            <span className="focus-now-label">
              {focusNow ? "Focus Mode on" : "Focus Now"}
            </span>
            <span className="focus-now-sub">
              {focusNow ? "ambient & low-energy picks" : "one-click ambient preset"}
            </span>
          </span>
        </button>

        <div className="tempo-chips" role="radiogroup" aria-label="tempo bucket">
          {TEMPO_OPTIONS.map((opt) => {
            const active = tempo === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={active}
                className={`tempo-chip ${active ? "tempo-chip--on" : ""}`}
                onClick={() => setTempo(opt.value)}
                title={opt.sub}
              >
                <span className="tempo-chip-label">{opt.label}</span>
                <span className="tempo-chip-sub">{opt.sub}</span>
              </button>
            );
          })}
        </div>

        {anyActive && (
          <button
            type="button"
            className="focus-reset"
            onClick={reset}
            title="clear focus filters"
          >
            clear
          </button>
        )}
      </div>
    </section>
  );
}
