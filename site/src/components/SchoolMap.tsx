import { useRefinementList } from "react-instantsearch";

/**
 * De School floorplan (real Illustrator SVG from hetarchief) shown as
 * an atmospheric blueprint plate — art, not UI. The interactive room
 * picker lives beside it as its own strip: one card per room, clickable,
 * disjunctive (multi-select via InstantSearch default OR refinement).
 *
 * The plan has 9 numbered rooms. Our archive has sets from 8 of them
 * (De Cinema is on the plan but we scraped no sets for it).
 */

type Room = {
  value: string;
  label: string;
  sub: string;
  number: number;
};

const ROOMS: Room[] = [
  { value: "De Club", label: "De Club", sub: "the gym", number: 1 },
  { value: "De Aula", label: "De Aula", sub: "auditorium", number: 2 },
  { value: "De Meetkamer", label: "De Meetkamer", sub: "meeting room", number: 3 },
  { value: "Het Muzieklokaal", label: "Het Muzieklokaal", sub: "music room", number: 4 },
  { value: "De Cinema", label: "De Cinema", sub: "cinema", number: 5 },
  { value: "COTL", label: "COTL", sub: "annex", number: 6 },
  { value: "De Binnentuin", label: "De Binnentuin", sub: "courtyard", number: 7 },
  { value: "De Lasserij", label: "De Lasserij", sub: "workshop", number: 8 },
  { value: "Het Terras", label: "Het Terras", sub: "terrace", number: 9 },
];

export function SchoolMap() {
  const { items, refine } = useRefinementList({
    attribute: "space",
    limit: 20,
  });

  const byValue = new Map(items.map((i) => [i.value, i]));
  const maxCount = Math.max(1, ...items.map((i) => i.count));
  const activeCount = items.filter((i) => i.isRefined).length;
  const activeNums = ROOMS.filter(
    (r) => byValue.get(r.value)?.isRefined,
  ).map((r) => r.number);

  return (
    <section className="school-map-wrap">
      <header className="school-map-head">
        <div>
          <span className="plate-eyebrow">Plate II · Floor Plan</span>
          <span className="school-map-title">The School — a plan</span>
        </div>
        <span className="school-map-hint">
          select one or more rooms{" "}
          <span className="muted">· disjunctive OR</span>
          {activeCount > 0 && (
            <span className="school-map-active">
              {" "}· {activeCount} active
            </span>
          )}
        </span>
      </header>

      <div className="school-map-grid">
        {/* Blueprint plate — atmospheric backdrop with selected-room overlay */}
        <figure className={`school-plate ${activeCount > 0 ? "school-plate--active" : ""}`}>
          <img
            src="/school-plan.svg"
            alt="Floor plan of De School Amsterdam (1960, adapted 2016)"
            className="school-backdrop"
          />
          {activeNums.length > 0 && (
            <div className="school-plate-highlight" aria-hidden>
              <span className="school-plate-highlight-label">
                rooms in session
              </span>
              <span className="school-plate-highlight-nums">
                {activeNums.map((n) => (
                  <span key={n} className="school-plate-num">
                    {n}
                  </span>
                ))}
              </span>
            </div>
          )}
          <figcaption className="school-plate-caption">
            a schematic from hetarchief · not to scale
          </figcaption>
        </figure>

        {/* Room picker — the actual UI */}
        <ol className="school-rooms">
          {ROOMS.map((r) => {
            const item = byValue.get(r.value);
            const count = item?.count ?? 0;
            const active = item?.isRefined ?? false;
            const disabled = !item || count === 0;
            const intensity = count / maxCount;

            return (
              <li key={r.value}>
                <button
                  type="button"
                  className={`room-card ${active ? "room-card--on" : ""} ${
                    disabled ? "room-card--off" : ""
                  }`}
                  disabled={disabled}
                  onClick={() => item && refine(r.value)}
                  aria-pressed={active}
                >
                  <span className="room-card-num" aria-hidden>
                    {r.number}
                  </span>
                  <span className="room-card-body">
                    <span className="room-card-name">{r.label}</span>
                    <span className="room-card-sub">{r.sub}</span>
                  </span>
                  <span className="room-card-count">
                    {count > 0 ? count.toLocaleString("nl-NL") : "—"}
                  </span>
                  <span
                    className="room-card-bar"
                    style={{ width: `${intensity * 100}%` }}
                    aria-hidden
                  />
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
