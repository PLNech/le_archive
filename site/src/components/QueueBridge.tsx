import { useEffect, useRef } from "react";
import { useHits } from "react-instantsearch";
import type { SetRecord } from "../types";
import { usePlayerStore } from "../hooks/usePlayerStore";
import { useQueueStore } from "../hooks/useQueueStore";

/**
 * Lives inside <InstantSearch> so `useHits` works. Listens for the
 * `player:ended` CustomEvent fired by Player when the Mixcloud widget
 * ends, then advances to the next playable hit in the current results.
 *
 * Wraps around if we hit the end of the current page. Doesn't paginate —
 * user can if they want to keep going past ~20 sets.
 */
export function QueueBridge() {
  const { items } = useHits<SetRecord>();
  const play = usePlayerStore((s) => s.play);
  const hitsRef = useRef<SetRecord[]>(items);

  useEffect(() => {
    hitsRef.current = items;
  }, [items]);

  useEffect(() => {
    const onEnded = (event: Event) => {
      if (!useQueueStore.getState().autoAdvance) return;
      const detail = (event as CustomEvent<{ objectID: string }>).detail;
      const hits = hitsRef.current;
      if (!detail || hits.length === 0) return;
      const idx = hits.findIndex((h) => h.objectID === detail.objectID);
      // Start search after the current set; if not found, start from top.
      const startAt = idx >= 0 ? idx + 1 : 0;
      for (let step = 0; step < hits.length; step++) {
        const next = hits[(startAt + step) % hits.length];
        if (next.objectID === detail.objectID) continue;
        if (!next.mixcloud_url) continue;
        play({
          objectID: next.objectID,
          artists: next.artists,
          date: next.date,
          space: next.space,
          event: next.event,
          mixcloudUrl: next.mixcloud_url,
          coverUrl: next.cover_url,
          duration: next.duration,
          fingerprint: next.viz_fingerprint,
          similarBySound: next.similar_by_sound,
        });
        return;
      }
    };
    window.addEventListener("player:ended", onEnded);
    return () => window.removeEventListener("player:ended", onEnded);
  }, [play]);

  return null;
}
