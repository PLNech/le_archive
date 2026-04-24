import aa from "search-insights";

const APP_ID = import.meta.env.VITE_ALGOLIA_APP_ID as string | undefined;
const SEARCH_KEY = import.meta.env.VITE_ALGOLIA_SEARCH_API_KEY as
  | string
  | undefined;
const INDEX = "archive_sets";

const TOKEN_STORAGE_KEY = "learchive-user-token";

function makeToken(): string {
  const rnd =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `anon-${rnd}`;
}

function getOrCreateToken(): string {
  try {
    const existing = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (existing) return existing;
    const next = makeToken();
    localStorage.setItem(TOKEN_STORAGE_KEY, next);
    return next;
  } catch {
    return makeToken();
  }
}

let initialized = false;
let enabled = false;
const sentViews = new Set<string>();
const sentConversions = new Set<string>();

export function initInsights(): void {
  if (initialized || !APP_ID || !SEARCH_KEY) {
    initialized = true;
    return;
  }
  try {
    aa("init", {
      appId: APP_ID,
      apiKey: SEARCH_KEY,
      useCookie: false,
    });
    aa("setUserToken", getOrCreateToken());
    enabled = true;
  } catch {
    enabled = false;
  }
  initialized = true;
}

export const insightsEnabled = (): boolean => enabled;

export function trackView(objectIDs: string[]): void {
  if (!enabled || objectIDs.length === 0) return;
  const fresh = objectIDs.filter((id) => !sentViews.has(id));
  if (fresh.length === 0) return;
  fresh.forEach((id) => sentViews.add(id));
  try {
    for (let i = 0; i < fresh.length; i += 20) {
      aa("viewedObjectIDs", {
        index: INDEX,
        eventName: "Set Viewed",
        objectIDs: fresh.slice(i, i + 20),
      });
    }
  } catch {
    /* silent */
  }
}

export function trackClick(objectID: string, eventName = "Set Played"): void {
  if (!enabled) return;
  try {
    aa("clickedObjectIDs", {
      index: INDEX,
      eventName,
      objectIDs: [objectID],
    });
  } catch {
    /* silent */
  }
}

export function trackConversion(
  objectID: string,
  eventName = "Sustained Listen 3min",
): void {
  if (!enabled) return;
  const key = `${objectID}|${eventName}`;
  if (sentConversions.has(key)) return;
  sentConversions.add(key);
  try {
    aa("convertedObjectIDs", {
      index: INDEX,
      eventName,
      objectIDs: [objectID],
    });
  } catch {
    /* silent */
  }
}
