import { Blocks, ExternalLink, FileText, Github, MessageCircle, Sparkles } from "lucide-react";
import type { ComponentType } from "react";
import type { FeedItem, FeedItemType } from "../types";

const typePresentation: Record<FeedItemType, { label: string; icon: ComponentType<{ size?: number }> }> = {
  paper: { label: "Paper", icon: FileText },
  github_repo: { label: "GitHub Repository", icon: Github },
  github_skill: { label: "GitHub Skill", icon: Blocks },
  ai_news: { label: "AI News", icon: Sparkles },
  x_post: { label: "X Post", icon: MessageCircle },
};
const trendingGainLabels: Record<string, string> = {
  daily: "today",
  weekly: "this week",
  monthly: "this month",
};

export function FeedCard({
  item,
  topicNames,
}: {
  item: FeedItem;
  topicNames: Record<string, string>;
}) {
  const presentation = typePresentation[item.type];
  const Icon = presentation.icon;
  const detail = typeDetail(item);
  const aiSummary = item.metadata.summary_kind === "ai";

  return (
    <article className={`feed-card feed-card-${item.type}`}>
      <div className="feed-card-meta">
        <span className="feed-type"><Icon size={13} />{presentation.label}</span>
        <span>{item.source}</span>
        {item.published_at ? <time dateTime={item.published_at}>{formatDate(item.published_at)}</time> : null}
      </div>
      <div className="feed-card-heading">
        <div>
          <h2>{item.title}</h2>
          {item.authors.length > 0 ? <p className="feed-authors">{item.authors.join(", ")}</p> : null}
        </div>
        <a href={item.url} target="_blank" rel="noreferrer" aria-label={`Open ${item.title}`}>
          <ExternalLink size={15} />
        </a>
      </div>
      {item.summary ? (
        <div className="feed-summary-block">
          {aiSummary ? <span className="feed-summary-label"><Sparkles size={11} />AI summary</span> : null}
          <p className="feed-summary">{item.summary}</p>
        </div>
      ) : null}
      <div className="feed-card-footer">
        <div className="feed-topics">
          {item.topics.map((topic) => <span key={topic}>{topicNames[topic] ?? topic}</span>)}
        </div>
        {detail ? <span className="feed-detail">{detail}</span> : null}
      </div>
    </article>
  );
}

function typeDetail(item: FeedItem): string | null {
  if (item.type === "paper") {
    const venue = typeof item.metadata.venue === "string" ? item.metadata.venue : null;
    const doi = typeof item.metadata.doi === "string" ? `DOI ${item.metadata.doi}` : null;
    const citations = typeof item.metadata.cited_by_count === "number"
      ? `${item.metadata.cited_by_count} citations`
      : null;
    return [venue, doi, citations].filter(Boolean).join(" | ") || null;
  }
  if (item.type === "github_repo") {
    const rank = typeof item.metadata.rank === "number" ? `Rank #${item.metadata.rank}` : null;
    const language = typeof item.metadata.language === "string" ? item.metadata.language : null;
    const stars = typeof item.metadata.stars === "number"
      ? `${item.metadata.stars.toLocaleString()} stars`
      : null;
    const forks = typeof item.metadata.forks === "number"
      ? `${item.metadata.forks.toLocaleString()} forks`
      : null;
    const period = typeof item.metadata.period === "string" ? item.metadata.period : "";
    const starsPeriod = typeof item.metadata.stars_period === "number"
      ? `${item.metadata.stars_period.toLocaleString()} ${trendingGainLabels[period] ?? "in period"}`
      : null;
    return [rank, language, stars, forks, starsPeriod].filter(Boolean).join(" · ") || null;
  }
  if (item.type === "github_skill" && typeof item.metadata.repository === "string") return item.metadata.repository;
  if (item.type === "ai_news" && typeof item.metadata.publisher === "string") return item.metadata.publisher;
  if (item.type === "x_post" && typeof item.metadata.handle === "string") return item.metadata.handle;
  return null;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}
