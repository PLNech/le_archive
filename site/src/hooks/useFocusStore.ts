import { create } from "zustand";

export type TempoSelection = "any" | "slow" | "mid" | "fast";

type State = {
  focusNow: boolean;
  tempo: TempoSelection;
  toggleFocus: () => void;
  setTempo: (t: TempoSelection) => void;
  reset: () => void;
};

export const useFocusStore = create<State>((set) => ({
  focusNow: false,
  tempo: "any",
  toggleFocus: () => set((s) => ({ focusNow: !s.focusNow })),
  setTempo: (t) => set({ tempo: t }),
  reset: () => set({ focusNow: false, tempo: "any" }),
}));

/**
 * Compose the Algolia `filters` string from current focus state.
 * Returns `""` when nothing is active so <Configure> stays a no-op.
 *
 *  - Focus Now preset: energy_mean ≤ 0.18 (ambient / low-energy).
 *    Numeric filter automatically excludes unenriched records, so this
 *    implicitly gates on _enrichment.audio = true.
 *  - Tempo pick: tempo_bucket equality.
 */
export function composeFocusFilters(s: {
  focusNow: boolean;
  tempo: TempoSelection;
}): string {
  const parts: string[] = [];
  if (s.focusNow) parts.push("energy_mean:0 TO 0.18");
  if (s.tempo !== "any") parts.push(`tempo_bucket:${s.tempo}`);
  return parts.join(" AND ");
}
