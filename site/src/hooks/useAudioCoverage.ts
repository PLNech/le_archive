import { useEffect, useState } from "react";
import { searchClient, INDEX_NAME, hasCredentials } from "../lib/algolia";

export type Coverage = { analyzed: number; total: number };

type SearchResult = {
  results: Array<{ nbHits?: number }>;
};

/**
 * Poll Algolia for `_enrichment.audio=true` vs total counts, so we can show
 * a live "X of N analyzed" indicator while the P6 worker runs in the
 * background. 30s poll — cheap, low visibility lag.
 */
export function useAudioCoverage(): Coverage | null {
  const [data, setData] = useState<Coverage | null>(null);

  useEffect(() => {
    if (!hasCredentials) return;
    let cancelled = false;

    async function run() {
      try {
        const res = (await searchClient.search({
          requests: [
            {
              indexName: INDEX_NAME,
              params: "",
              filters: "_enrichment.audio:true",
              hitsPerPage: 0,
            },
            { indexName: INDEX_NAME, params: "", hitsPerPage: 0 },
          ],
        })) as unknown as SearchResult;
        if (cancelled) return;
        const analyzed = res.results?.[0]?.nbHits ?? 0;
        const total = res.results?.[1]?.nbHits ?? 0;
        setData({ analyzed, total });
      } catch {
        /* transient network hiccup — next tick will retry */
      }
    }

    run();
    const t = setInterval(run, 30_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return data;
}
