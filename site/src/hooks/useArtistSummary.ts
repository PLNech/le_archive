import { useEffect, useState } from "react";

export type WikiSummary = {
  title: string;
  extract: string;
  description?: string;
  thumbnail?: { source: string; width: number; height: number };
  content_urls?: { desktop?: { page: string } };
};

export type ArtistStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "found"; summary: WikiSummary }
  | { state: "not-found" };

const cache = new Map<string, ArtistStatus>();

const VARIANTS: ((n: string) => string)[] = [
  (n) => n,
  (n) => `${n} (DJ)`,
  (n) => `${n} (musician)`,
  (n) => `${n} (producer)`,
  (n) => `${n} (band)`,
];

async function fetchVariant(
  title: string,
  signal: AbortSignal,
): Promise<WikiSummary | null> {
  const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(
    title.replace(/ /g, "_"),
  )}`;
  const res = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) return null;
  const json = (await res.json()) as WikiSummary & { type?: string };
  if (json.type === "disambiguation") return null;
  if (!json.extract) return null;
  return json;
}

export function useArtistSummary(name: string | null): ArtistStatus {
  const [status, setStatus] = useState<ArtistStatus>({ state: "idle" });

  useEffect(() => {
    if (!name) {
      setStatus({ state: "idle" });
      return;
    }

    const cached = cache.get(name);
    if (cached) {
      setStatus(cached);
      return;
    }

    setStatus({ state: "loading" });
    const ctrl = new AbortController();

    (async () => {
      for (const variant of VARIANTS) {
        try {
          const summary = await fetchVariant(variant(name), ctrl.signal);
          if (summary) {
            const result: ArtistStatus = { state: "found", summary };
            cache.set(name, result);
            setStatus(result);
            return;
          }
        } catch (err) {
          if ((err as Error).name === "AbortError") return;
        }
      }
      const result: ArtistStatus = { state: "not-found" };
      cache.set(name, result);
      setStatus(result);
    })();

    return () => ctrl.abort();
  }, [name]);

  return status;
}
