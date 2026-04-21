import { algoliasearch } from "algoliasearch";

const APP_ID = import.meta.env.VITE_ALGOLIA_APP_ID as string | undefined;
const SEARCH_KEY = import.meta.env.VITE_ALGOLIA_SEARCH_API_KEY as
  | string
  | undefined;

export const INDEX_NAME = "archive_sets";

export const searchClient = (() => {
  if (!APP_ID || !SEARCH_KEY) {
    // Stub client so dev server still boots before creds are wired up.
    // All requests resolve to empty hits.
    return {
      search: async () => ({
        results: [
          { hits: [], nbHits: 0, page: 0, nbPages: 0, hitsPerPage: 20 },
        ],
      }),
    } as unknown as ReturnType<typeof algoliasearch>;
  }
  return algoliasearch(APP_ID, SEARCH_KEY);
})();

export const hasCredentials = Boolean(APP_ID && SEARCH_KEY);
