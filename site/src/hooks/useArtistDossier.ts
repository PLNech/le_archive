import { useEffect, useState } from "react";
import { searchClient, ARTISTS_INDEX, hasCredentials } from "../lib/algolia";

export type ArtistDossier = {
  objectID: string;
  name: string;
  discogs_id?: number;
  discogs_url?: string;
  lastfm_url?: string;
  listeners?: number;
  playcount?: number;
  tags?: string[];
  similar?: string[];
  profile?: string;
  bio_snippet?: string;
  aliases?: string[];
};

export type DossierStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "found"; dossier: ArtistDossier }
  | { state: "not-found" };

const cache = new Map<string, DossierStatus>();

function normalize(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

export function useArtistDossier(name: string | null): DossierStatus {
  const [status, setStatus] = useState<DossierStatus>({ state: "idle" });

  useEffect(() => {
    if (!name || !hasCredentials) return;

    const key = normalize(name);
    const cached = cache.get(key);
    if (cached) {
      // Sync cache hit → reflect it immediately. One render, no cascade.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus(cached);
      return;
    }

    let aborted = false;
    setStatus({ state: "loading" });

    (async () => {
      try {
        const res = await searchClient.search<ArtistDossier>({
          requests: [
            {
              indexName: ARTISTS_INDEX,
              params: "",
              filters: `objectID:${JSON.stringify(key)}`,
              hitsPerPage: 1,
            },
          ],
        });
        if (aborted) return;
        // @ts-expect-error algolia result union is wide
        const hit = res.results?.[0]?.hits?.[0] as ArtistDossier | undefined;
        if (!hit) {
          const miss: DossierStatus = { state: "not-found" };
          cache.set(key, miss);
          setStatus(miss);
          return;
        }
        const found: DossierStatus = { state: "found", dossier: hit };
        cache.set(key, found);
        setStatus(found);
      } catch {
        if (aborted) return;
        setStatus({ state: "not-found" });
      }
    })();

    return () => {
      aborted = true;
    };
  }, [name]);

  // Derived: when the modal is closed (name === null), show idle even if a
  // prior lookup left `status` populated. Avoids setState-in-effect just to reset.
  if (!name) return { state: "idle" };
  return status;
}
