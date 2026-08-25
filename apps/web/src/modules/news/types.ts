export type FeedItemType = "paper" | "github_repo" | "github_skill" | "ai_news" | "x_post";

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
