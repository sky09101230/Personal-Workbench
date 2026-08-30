export type FeedItemType = "paper" | "github_repo" | "github_skill" | "ai_news" | "x_post";
export type TrendingPeriod = "daily" | "weekly" | "monthly";
export type RadarReviewStatus = "new" | "seen" | "interested" | "dismissed";

export type FeedItem = {
  id: string;
  type: FeedItemType;
  source: string;
  title: string;
  summary: string | null;
  url: string;
  authors: string[];
  published_at: string | null;
  fetched_at: string | null;
  topics: string[];
  metadata: Record<string, unknown>;
  read: boolean;
  saved: boolean;
  hidden: boolean;
};

export type Topic = {
  id: string;
  name: string;
  keywords: string[];
  negative_keywords: string[];
  enabled_sources: string[];
};

export type FeedPage = {
  items: FeedItem[];
  total: number;
  limit: number;
  offset: number;
};

export type TopicList = {
  items: Topic[];
};

export type RefreshResult = {
  status: "succeeded";
  providers: string[];
  fetched: number;
  stored: number;
  topic_matches: number;
  refreshed_at: string;
};

export type RadarSourceStatus = {
  name: string;
  status: "success" | "degraded" | "failed" | "not_attempted";
  attempts: number;
  routes: Record<string, unknown>[];
  result_count: number;
  warning: string | null;
};

export type RadarPaper = {
  recommendation_id: string;
  paper_id: string;
  selection_kind: "recommended" | "verified_not_selected";
  selection_rank: number | null;
  title: string;
  authors: string[];
  doi: string | null;
  arxiv_id: string | null;
  published_at: string | null;
  venue: string | null;
  publication_type: string | null;
  url: string;
  ai_summary: string;
  recommendation_reason: string;
  relevance_score: number | null;
  novelty_score: number | null;
  scientific_value_score: number | null;
  recency_score: number | null;
  overall_score: number | null;
  relationship_to_library: string | null;
  zotero_relationship: Record<string, unknown>;
  date_evidence: Record<string, unknown>;
  evidence: Record<string, unknown>;
  source: Record<string, unknown>;
  review_status: RadarReviewStatus;
};

export type RadarRun = {
  id: string;
  task_key: string;
  run_key: string;
  generated_at: string;
  ingested_at: string;
  profile: Record<string, unknown>;
  search_window: Record<string, unknown>;
  candidate_count: number;
  verified_candidate_count: number;
  recommended_count: number;
  warnings: string[];
  source_status: RadarSourceStatus[];
  zotero_context: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  recommendations: RadarPaper[];
  verified_alternatives: RadarPaper[];
};

export type RadarLatestResponse = {
  run: RadarRun | null;
};

export type RadarReviewResponse = {
  recommendation_id: string;
  review_status: RadarReviewStatus;
};
