import { useEffect, useState } from "react";
import { searchClient, INDEX_NAME } from "../lib/algolia";
import type { SetRecord } from "../types";

type State =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready"; sets: SetRecord[] }
  | { state: "error"; message: string };

type AlgoliaResult = { results: Array<{ hits: SetRecord[] }> };

/**
 * Fetch every archived set by a given artist, most-recent first.
 *
 * Cached per-artist in-module — the dossier modal can open/close without
 * re-hitting Algolia. `hitsPerPage: 100` is generous headroom; the most
 * prolific De School faculty member has ~25 sets in the archive.
 */
const cache = new Map<string, SetRecord[]>();

export function useArtistSets(name: string | null | undefined): State {
  const key = (name ?? "").trim().toLowerCase();

  const [async, setAsync] = useState<State>({ state: "loading" });

  useEffect(() => {
    if (!key) return;
    if (cache.has(key)) return;
    let cancelled = false;

    searchClient
      .search<SetRecord>({
        requests: [
          {
            indexName: INDEX_NAME,
            params: "",
            hitsPerPage: 100,
            filters: `artists:${JSON.stringify(name)}`,
          },
        ],
      })
      .then((res) => {
        if (cancelled) return;
        const { results } = res as unknown as AlgoliaResult;
        const hits = results[0]?.hits ?? [];
        const sorted = [...hits].sort(
          (a, b) => (b.date_ts ?? 0) - (a.date_ts ?? 0),
        );
        cache.set(key, sorted);
        setAsync({ state: "ready", sets: sorted });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setAsync({
          state: "error",
          message: e instanceof Error ? e.message : "unknown",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [key, name]);

  if (!key) return { state: "idle" };
  const hit = cache.get(key);
  if (hit) return { state: "ready", sets: hit };
  return async;
}
