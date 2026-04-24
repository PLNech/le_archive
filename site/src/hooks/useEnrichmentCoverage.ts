import { useEffect, useState } from "react";
import { searchClient, INDEX_NAME, hasCredentials } from "../lib/algolia";

export type EnrichmentCoverage = {
  audio: number;
  artists: number;
  mood: number;
  mixcloud: number;
  total: number;
};

type SearchResult = {
  results: Array<{ nbHits?: number }>;
};

const FLAGS = ["audio", "artists", "mood", "mixcloud"] as const;
type Flag = (typeof FLAGS)[number];

/**
 * Poll Algolia every 20s for per-enrichment-flag coverage. One batched
 * multi-index search, so it's cheap even while two background workers run.
 */
export function useEnrichmentCoverage(): EnrichmentCoverage | null {
  const [data, setData] = useState<EnrichmentCoverage | null>(null);

  useEffect(() => {
    if (!hasCredentials) return;
    let cancelled = false;

    async function run() {
      try {
        const queries = [
          ...FLAGS.map((f) => ({
            indexName: INDEX_NAME,
            query: "",
            filters: `_enrichment.${f}:true`,
            hitsPerPage: 0,
          })),
          { indexName: INDEX_NAME, query: "", hitsPerPage: 0 },
        ];
        const res = (await searchClient.search(queries)) as unknown as SearchResult;
        if (cancelled) return;
        const counts = res.results.map((r) => r?.nbHits ?? 0);
        setData({
          audio: counts[0],
          artists: counts[1],
          mood: counts[2],
          mixcloud: counts[3],
          total: counts[4],
        });
      } catch {
        /* transient network — next tick retries */
      }
    }

    run();
    const t = setInterval(run, 20_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return data;
}

export function flagFilter(active: Flag[]): string {
  if (active.length === 0) return "";
  return active.map((f) => `_enrichment.${f}:true`).join(" AND ");
}

export const ALL_FLAGS = FLAGS;
export type EnrichmentFlag = Flag;
