import { create } from "zustand";
import { persist } from "zustand/middleware";

type State = {
  ids: Record<string, true>;
  onlyFavorites: boolean;
  toggle: (id: string) => void;
  setOnlyFavorites: (v: boolean) => void;
  clear: () => void;
};

export const useFavoritesStore = create<State>()(
  persist(
    (set) => ({
      ids: {},
      onlyFavorites: false,
      toggle: (id) =>
        set((s) => {
          const next = { ...s.ids };
          if (next[id]) delete next[id];
          else next[id] = true;
          return { ids: next };
        }),
      setOnlyFavorites: (v) => set({ onlyFavorites: v }),
      clear: () => set({ ids: {}, onlyFavorites: false }),
    }),
    { name: "learchive-favorites" },
  ),
);

/** Build the Algolia filter string for the favorites-only view. */
export function composeFavoritesFilters(ids: string[]): string {
  if (ids.length === 0) {
    // Active toggle + no favorites → match nothing (shows empty state).
    return "objectID:__no_favorites__";
  }
  return ids.map((id) => `objectID:${JSON.stringify(id)}`).join(" OR ");
}
