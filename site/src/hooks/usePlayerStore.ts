import { create } from "zustand";

export type PlayingSet = {
  objectID: string;
  artists: string[];
  date: string;
  space: string;
  event: string;
  mixcloudUrl: string;
  coverUrl?: string;
  duration?: number;
  fingerprint?: {
    bands: number;
    frame_seconds: number;
    n_frames: number;
    data_b64: string;
  };
};

type PlayerState = {
  current: PlayingSet | null;
  play: (set: PlayingSet) => void;
  stop: () => void;
};

export const usePlayerStore = create<PlayerState>((set) => ({
  current: null,
  play: (s) => set({ current: s }),
  stop: () => set({ current: null }),
}));
