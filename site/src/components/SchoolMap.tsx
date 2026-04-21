import { useRefinementList } from "react-instantsearch";

/**
 * Real De School floorplan (Illustrator SVG from hetarchief) rendered as
 * a blueprint plate: cream paths on ink background. Clickable hitboxes
 * sit over the approximate room positions — multi-select (disjunctive
 * faceting is the InstantSearch default).
 *
 * Coordinates are in the plan's native viewBox (755.5 × 454.5) and
 * converted to % for responsive positioning over the <img> backdrop.
 *
 * Positions are approximate first-pass — expected to need calibration.
 */

const VB_W = 755.5;
const VB_H = 454.5;

type Room = {
  value: string;
  label: string;
  sub: string;
  number: number;
  // rect in the plan's coordinate system
  x: number;
  y: number;
  w: number;
  h: number;
};

const ROOMS: Room[] = [
  // 1 — DE CLUB (right-hand hatched block, the main dancefloor, 559 sets)
  { value: "De Club", label: "De Club", sub: "the gym", number: 1, x: 560, y: 135, w: 195, h: 245 },
  // 2 — DE AULA (bottom-right hatched — auditorium, 16 sets)
  { value: "De Aula", label: "De Aula", sub: "auditorium", number: 2, x: 460, y: 295, w: 100, h: 85 },
  // 3 — DE MEETKAMER (small top-left room, 7 sets)
  { value: "De Meetkamer", label: "De Meetkamer", sub: "meeting room", number: 3, x: 268, y: 140, w: 90, h: 70 },
  // 4 — HET MUZIEKLOKAAL (top-center classroom, second dancefloor, 248 sets)
  { value: "Het Muzieklokaal", label: "Het Muzieklokaal", sub: "music room", number: 4, x: 360, y: 140, w: 100, h: 75 },
  // 5 — DE CINEMA (center-left, long room) — NO SETS in our data but exists on plan
  { value: "De Cinema", label: "De Cinema", sub: "cinema", number: 5, x: 360, y: 220, w: 70, h: 75 },
  // 6 — COTL (top-mid annex, 7 sets)
  { value: "COTL", label: "COTL", sub: "annex", number: 6, x: 462, y: 140, w: 90, h: 70 },
  // 7 — DE BINNENTUIN (inner courtyard, center big room, 25 sets)
  { value: "De Binnentuin", label: "De Binnentuin", sub: "courtyard", number: 7, x: 268, y: 220, w: 90, h: 160 },
  // 8 — DE LASSERIJ (top-right annex, welding shop, 22 sets)
  { value: "De Lasserij", label: "De Lasserij", sub: "workshop", number: 8, x: 650, y: 8, w: 100, h: 90 },
  // 9 — HET TERRAS (outdoor terrace, 7 sets) — bottom-left outdoor area
  { value: "Het Terras", label: "Het Terras", sub: "terrace", number: 9, x: 60, y: 395, w: 140, h: 50 },
];

function pct(n: number, denom: number): string {
  return `${((n / denom) * 100).toFixed(3)}%`;
}

export function SchoolMap() {
  const { items, refine } = useRefinementList({
    attribute: "space",
    limit: 20,
  });

  const byValue = new Map(items.map((i) => [i.value, i]));
  const refined = new Set(items.filter((i) => i.isRefined).map((i) => i.value));
  const maxCount = Math.max(1, ...items.map((i) => i.count));

  return (
    <div className="school-map-wrap">
      <header className="school-map-head">
        <div>
          <span className="school-map-eyebrow">Fig. 1</span>
          <span className="school-map-title">The School — a plan</span>
        </div>
        <span className="school-map-hint">
          click one or more rooms to filter
          <span className="muted"> · disjunctive OR</span>
        </span>
      </header>

      <div className="school-plate">
        <img
          src="/school-plan.svg"
          alt="Floor plan of De School Amsterdam"
          className="school-backdrop"
        />

        {ROOMS.map((r) => {
          const item = byValue.get(r.value);
          const count = item?.count ?? 0;
          const active = refined.has(r.value);
          const intensity = count / maxCount;
          const disabled = !item || count === 0;

          return (
            <button
              key={r.value}
              type="button"
              disabled={disabled}
              onClick={() => item && refine(r.value)}
              className={`room-hitbox ${active ? "room-hitbox--on" : ""} ${
                disabled ? "room-hitbox--off" : ""
              }`}
              style={{
                left: pct(r.x, VB_W),
                top: pct(r.y, VB_H),
                width: pct(r.w, VB_W),
                height: pct(r.h, VB_H),
              }}
              title={
                disabled
                  ? `${r.label} (no sets in archive)`
                  : `${r.label} — ${count} set${count === 1 ? "" : "s"}${
                      active ? " · active" : ""
                    }`
              }
            >
              {/* Density fill — proportional bar at bottom of room */}
              <span
                className="room-density"
                style={{ width: `${intensity * 100}%` }}
                aria-hidden
              />
              <span className="room-num" aria-hidden>{r.number}</span>
              <span className="room-lab">
                <span className="room-lab-main">{r.label}</span>
                <span className="room-lab-count">
                  {count > 0 ? count.toLocaleString("nl-NL") : "—"}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <footer className="school-map-footer">
        <span>
          a schematic, not to scale · 8 rooms · 891 sets on file
        </span>
        <span className="muted">
          plan source: hetarchief.deschoolamsterdam.nl
        </span>
      </footer>
    </div>
  );
}
