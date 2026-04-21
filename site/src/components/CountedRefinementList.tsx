import { useRefinementList } from "react-instantsearch";
import type { UseRefinementListProps } from "react-instantsearch";

type Props = UseRefinementListProps & {
  /** Override for item label rendering (e.g. capitalize space names) */
  formatLabel?: (label: string) => string;
  /** Enable searchable facet (artists, events) */
  searchable?: boolean;
  searchablePlaceholder?: string;
};

export function CountedRefinementList({
  formatLabel = (l) => l,
  searchable,
  searchablePlaceholder,
  ...props
}: Props) {
  const {
    items,
    refine,
    searchForItems,
    isShowingMore,
    canToggleShowMore,
    toggleShowMore,
  } = useRefinementList(props);

  if (items.length === 0) {
    return <div className="facet-empty">no data yet</div>;
  }

  const maxCount = Math.max(...items.map((i) => i.count), 1);

  return (
    <div className="facet">
      {searchable && (
        <input
          className="facet-search"
          type="search"
          placeholder={searchablePlaceholder ?? "search…"}
          onChange={(e) => searchForItems(e.currentTarget.value)}
        />
      )}
      <ul className="facet-list">
        {items.map((item) => {
          const pct = (item.count / maxCount) * 100;
          return (
            <li
              key={item.value}
              className={`facet-item ${item.isRefined ? "facet-item--on" : ""}`}
            >
              <button
                type="button"
                onClick={() => refine(item.value)}
                className="facet-btn"
              >
                <span
                  className="facet-bar"
                  style={{ width: `${pct}%` }}
                  aria-hidden
                />
                <span className="facet-check" aria-hidden>
                  {item.isRefined ? "●" : "○"}
                </span>
                <span className="facet-label">{formatLabel(item.label)}</span>
                <span className="facet-count">{item.count.toLocaleString("nl-NL")}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {canToggleShowMore && (
        <button
          type="button"
          className="facet-more"
          onClick={toggleShowMore}
        >
          {isShowingMore ? "− less" : "+ more"}
        </button>
      )}
    </div>
  );
}
