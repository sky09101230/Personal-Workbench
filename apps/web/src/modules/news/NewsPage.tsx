import { AlertCircle, LoaderCircle, Newspaper, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getNewsJson, postNewsJson } from "./api";
import { FeedCard } from "./components/FeedCard";
import type { FeedItemType, FeedPage, RefreshResult, Topic, TopicList } from "./types";
import "./news.css";

const pageSize = 20;
const tabs: { label: string; refreshLabel: string; value: FeedItemType }[] = [
  { label: "Papers", refreshLabel: "Refresh papers", value: "paper" },
  { label: "GitHub", refreshLabel: "Refresh GitHub", value: "github_repo" },
  { label: "Skills", refreshLabel: "Refresh skills", value: "github_skill" },
  { label: "AI News", refreshLabel: "Refresh AI news", value: "ai_news" },
  { label: "X", refreshLabel: "Refresh X", value: "x_post" },
];

export function NewsPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [feed, setFeed] = useState<FeedPage | null>(null);
  const [typeFilter, setTypeFilter] = useState<FeedItemType>("paper");
  const [topicFilter, setTopicFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const loadFeed = useCallback(async () => {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
    if (typeFilter) params.set("type", typeFilter);
    if (typeFilter === "paper" && topicFilter) params.set("topic", topicFilter);
    setLoading(true);
    setError(false);
    try {
      setFeed(await getNewsJson<FeedPage>(`/api/news/feed?${params}`));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, topicFilter, typeFilter]);

  useEffect(() => {
    void getNewsJson<TopicList>("/api/news/topics")
      .then((result) => setTopics(result.items))
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    void loadFeed();
  }, [loadFeed]);

  const topicNames = useMemo(
    () => Object.fromEntries(topics.map((topic) => [topic.id, topic.name])),
    [topics],
  );
  const activeTab = tabs.find((tab) => tab.value === typeFilter) ?? tabs[0];

  const refresh = async () => {
    setRefreshing(true);
    setError(false);
    try {
      await postNewsJson<RefreshResult>(`/api/news/refresh?type=${typeFilter}`);
      const result = await getNewsJson<TopicList>("/api/news/topics");
      setTopics(result.items);
      if (offset !== 0) setOffset(0);
      else await loadFeed();
    } catch {
      setError(true);
    } finally {
      setRefreshing(false);
    }
  };

  const selectType = (value: FeedItemType) => {
    setTypeFilter(value);
    setOffset(0);
  };

  const selectTopic = (value: string) => {
    setTopicFilter(value);
    setOffset(0);
  };

  return (
    <section className="news-page">
      <header className="news-header">
        <div>
          <h1>News</h1>
          <p>Discover, filter, and browse external research signals.</p>
        </div>
      </header>

      <div className="news-controls">
        <div className="news-tabs" role="tablist" aria-label="News item type">
          {tabs.map((tab) => (
            <button
              className={typeFilter === tab.value ? "active" : ""}
              type="button"
              role="tab"
              aria-selected={typeFilter === tab.value}
              onClick={() => selectType(tab.value)}
              key={tab.label}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="news-control-actions">
          {typeFilter === "paper" ? (
            <label className="topic-filter">
              <span>Topic</span>
              <select value={topicFilter} onChange={(event) => selectTopic(event.target.value)}>
                <option value="">All topics</option>
                {topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.name}</option>)}
              </select>
            </label>
          ) : null}
          <button className="news-refresh" type="button" onClick={() => void refresh()} disabled={refreshing}>
            <RefreshCw className={refreshing ? "spin" : ""} size={15} />
            {refreshing ? "Refreshing" : activeTab.refreshLabel}
          </button>
        </div>
      </div>

      <div className="news-feed-scroll">
        {loading ? (
          <NewsState icon={<LoaderCircle className="spin" size={22} />} title="Loading News" message="Reading the local News cache." />
        ) : error ? (
          <NewsState icon={<AlertCircle size={22} />} title="News unavailable" message="The News API could not be reached. Try again after restarting the changed services." />
        ) : !feed || feed.items.length === 0 ? (
          <NewsState icon={<Newspaper size={22} />} title="No feed items" message="Refresh this tab or choose a different Topic." />
        ) : (
          <div className="feed-list">
            {feed.items.map((item) => <FeedCard item={item} topicNames={topicNames} key={item.id} />)}
          </div>
        )}
      </div>

      {feed && feed.total > pageSize ? (
        <footer className="news-pagination">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button>
          <span>{offset + 1}–{Math.min(offset + pageSize, feed.total)} of {feed.total}</span>
          <button type="button" disabled={offset + pageSize >= feed.total} onClick={() => setOffset(offset + pageSize)}>Next</button>
        </footer>
      ) : null}
    </section>
  );
}

function NewsState({ icon, title, message }: { icon: React.ReactNode; title: string; message: string }) {
  return (
    <div className="news-state">
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  );
}
