import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { EnrichmentFlag } from "./useEnrichmentCoverage";

type State = {
  activeFlags: EnrichmentFlag[];
  toggle: (flag: EnrichmentFlag) => void;
  clear: () => void;
};

/**
 * Debug strip state: which enrichment flags are being AND-filtered on.
 * Persists across sessions so the filter you left on is still on.
 */
export const useDebugStore = create<State>()(
  persist(
    (set) => ({
      activeFlags: [],
      toggle: (flag) =>
        set((s) => {
          const next = s.activeFlags.includes(flag)
            ? s.activeFlags.filter((f) => f !== flag)
            : [...s.activeFlags, flag];
          return { activeFlags: next };
        }),
      clear: () => set({ activeFlags: [] }),
    }),
    { name: "learchive-debug" },
  ),
);
