import { useFavoritesStore } from "../hooks/useFavoritesStore";

/**
 * Pill in the results toolbar showing favorites count + a toggle that
 * restricts the list to bookmarked sets. Hidden when empty to keep the
 * chrome minimal — first star you drop reveals it.
 */
export function FavoritesToggle() {
  const onlyFav = useFavoritesStore((s) => s.onlyFavorites);
  const setOnly = useFavoritesStore((s) => s.setOnlyFavorites);
  const count = useFavoritesStore((s) => Object.keys(s.ids).length);

  if (count === 0 && !onlyFav) return null;

  return (
    <button
      type="button"
      className={`fav-toggle ${onlyFav ? "fav-toggle--on" : ""}`}
      onClick={() => setOnly(!onlyFav)}
      aria-pressed={onlyFav}
      title={
        onlyFav
          ? "show all sets"
          : `show only your ${count} bookmarked set${count === 1 ? "" : "s"}`
      }
    >
      <span className="fav-toggle-star" aria-hidden>
        {onlyFav ? "★" : "☆"}
      </span>
      <span className="fav-toggle-count">
        {count.toLocaleString("nl-NL")}
      </span>
      <span className="fav-toggle-label">
        {onlyFav ? "only favorites" : "favorites"}
      </span>
    </button>
  );
}
