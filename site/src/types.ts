export type SetRecord = {
  objectID: string;
  slug: string;
  artists: string[];
  date: string;
  date_ts: number;
  year: number;
  weekday: string;
  space: string;
  event: string;
  tags: string[];
  is_b2b: boolean;
  comment_count: number;
  detail_url: string;
  mixcloud_url: string | null;
  // enrichment (populated progressively)
  duration?: number;
  duration_bucket?: "short" | "medium" | "long";
  play_count?: number;
  favorite_count?: number;
  mixcloud_tags?: string[];
  artist_genres?: string[];
  mood?: string[];
  energy?: number;
  focus_score?: number;
  tempo_bucket?: "slow" | "mid" | "fast";
  bpm?: number;
};
