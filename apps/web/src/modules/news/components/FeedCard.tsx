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
      {item.summary ? <p className="feed-summary">{item.summary}</p> : null}
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
  if (item.type === "paper" && typeof item.metadata.venue === "string") return item.metadata.venue;
  if (item.type === "github_repo") {
    const language = typeof item.metadata.language === "string" ? item.metadata.language : null;
    const stars = typeof item.metadata.stars === "number" ? `${item.metadata.stars} stars` : null;
    return [language, stars].filter(Boolean).join(" · ") || null;
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
