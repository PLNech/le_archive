import { useRefinementList } from "react-instantsearch";

/**
 * Renders year facet as a vertical-bar timeline across the full archive range
 * (2016–2024). Each bar is a clickable refinement toggle. Height scales to the
 * tallest year bucket. Missing years (none in archive) render as a blank slot.
 */
export function YearTimeline() {
  const { items, refine } = useRefinementList({
    attribute: "year",
    limit: 20,
    sortBy: ["name:asc"],
  });

  if (items.length === 0) return null;

  const counts = new Map<number, { count: number; isRefined: boolean }>();
  for (const it of items) {
    counts.set(parseInt(it.value, 10), {
      count: it.count,
      isRefined: it.isRefined,
    });
  }

  const years = Array.from(counts.keys());
  const min = Math.min(...years);
  const max = Math.max(...years);
  const span = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  const maxCount = Math.max(...items.map((i) => i.count), 1);
  const total = items.reduce((n, i) => n + i.count, 0);

  return (
    <div className="timeline" role="group" aria-label="year timeline">
      <div className="timeline-head">
        <span className="timeline-range">
          {min}–{max}
        </span>
        <span className="timeline-total">
          {total.toLocaleString("nl-NL")} sets
        </span>
      </div>
      <div className="timeline-bars">
        {span.map((y) => {
          const entry = counts.get(y);
          const h = entry ? (entry.count / maxCount) * 100 : 0;
          const isRefined = entry?.isRefined ?? false;
          const isEmpty = !entry;
          return (
            <button
              key={y}
              type="button"
              className={`timeline-bar ${isRefined ? "timeline-bar--on" : ""} ${
                isEmpty ? "timeline-bar--empty" : ""
              }`}
              onClick={() => entry && refine(String(y))}
              disabled={isEmpty}
              title={
                entry
                  ? `${y} · ${entry.count} sets${isRefined ? " · active" : ""}`
                  : `${y} · no sets`
              }
            >
              <span
                className="timeline-bar-fill"
                style={{ height: `${h}%` }}
                aria-hidden
              />
              <span className="timeline-bar-count" aria-hidden>
                {entry?.count ?? ""}
              </span>
              <span className="timeline-bar-year">
                '{String(y).slice(2)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
