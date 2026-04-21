import { create } from "zustand";

type State = {
  name: string | null;
  open: (name: string) => void;
  close: () => void;
};

export const useArtistModal = create<State>((set) => ({
  name: null,
  open: (name) => set({ name }),
  close: () => set({ name: null }),
}));
