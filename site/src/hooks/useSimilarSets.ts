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
 * Hydrate a list of objectIDs to full records via Algolia's multi-index
 * search. Caches in-module so flipping between sets doesn't re-fetch. A
 * thin layer — the expensive neighbour graph was precomputed offline and
 * stored as `similar_by_sound: string[]` on each record.
 */
const cache = new Map<string, SetRecord>();

export function useSimilarSets(ids: string[] | undefined): State {
  const key = (ids ?? []).join("|");
  // Derived "synchronous" state: idle when no ids, ready when all cached.
  const cachedAll = ids
    ? (ids.map((id) => cache.get(id)).filter(Boolean) as SetRecord[])
    : [];
  const allInCache = Boolean(ids && cachedAll.length === ids.length);

  const [async, setAsync] = useState<State>({ state: "loading" });

  useEffect(() => {
    if (!ids || ids.length === 0 || allInCache) return; // nothing to fetch
    let cancelled = false;

    // Build a single OR-joined filter query so all similar records come
    // back in one roundtrip.
    const filter = ids
      .map((id) => `objectID:${JSON.stringify(id)}`)
      .join(" OR ");

    searchClient
      .search<SetRecord>({
        requests: [
          {
            indexName: INDEX_NAME,
            params: "",
            hitsPerPage: ids.length,
            filters: filter,
          },
        ],
      })
      .then((res) => {
        if (cancelled) return;
        const { results } = res as unknown as AlgoliaResult;
        const hits = results[0]?.hits ?? [];
        hits.forEach((h) => cache.set(h.objectID, h));
        // Preserve the requested order (Algolia returns relevance-ordered).
        const ordered = ids
          .map((id) => cache.get(id))
          .filter(Boolean) as SetRecord[];
        setAsync({ state: "ready", sets: ordered });
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
    // `key` is a stable stringification of ids; re-runs only on content change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!ids || ids.length === 0) return { state: "idle" };
  if (allInCache) return { state: "ready", sets: cachedAll };
  return async;
}
