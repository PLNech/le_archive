import { create } from "zustand";
import { persist } from "zustand/middleware";

type State = {
  autoAdvance: boolean;
  setAutoAdvance: (v: boolean) => void;
};

export const useQueueStore = create<State>()(
  persist(
    (set) => ({
      autoAdvance: true,
      setAutoAdvance: (v) => set({ autoAdvance: v }),
    }),
    { name: "learchive-queue" },
  ),
);
