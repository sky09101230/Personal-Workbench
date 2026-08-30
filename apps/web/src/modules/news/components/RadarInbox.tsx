import {
  AlertCircle,
  AlertTriangle,
  BookOpenCheck,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getNewsJson, patchNewsJson } from "../api";
import type {
  RadarLatestResponse,
  RadarPaper,
  RadarReviewResponse,
  RadarReviewStatus,
  RadarRun,
} from "../types";

const reviewOptions: { label: string; value: RadarReviewStatus }[] = [
  { label: "New", value: "new" },
  { label: "Seen", value: "seen" },
  { label: "Interested", value: "interested" },
  { label: "Dismissed", value: "dismissed" },
];

export function RadarInbox() {
  const [run, setRun] = useState<RadarRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await getNewsJson<RadarLatestResponse>(
        "/api/news/papers/research/radar/latest",
      );
      setRun(response.run);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateReview = async (
    recommendationId: string,
    status: RadarReviewStatus,
  ) => {
    setUpdating(recommendationId);
    setReviewError(false);
    try {
      const response = await patchNewsJson<RadarReviewResponse>(
        `/api/news/papers/research/recommendations/${encodeURIComponent(recommendationId)}/review`,
        { status },
      );
      setRun((current) => current ? updateRunReview(current, response) : current);
    } catch {
      setReviewError(true);
    } finally {
      setUpdating(null);
    }
  };

  if (loading) {
    return (
      <RadarState
        icon={<LoaderCircle className="spin" size={22} />}
        title="Loading Radar Inbox"
        message="Reading the latest validated Literature Radar run."
      />
    );
  }
  if (error) {
    return (
      <RadarState
        icon={<AlertCircle size={22} />}
        title="Radar Inbox unavailable"
        message="The persisted Radar run could not be read from Workbench."
        action={<button type="button" onClick={() => void load()}>Try again</button>}
      />
    );
  }
  if (!run) {
    return (
      <RadarState
        icon={<Sparkles size={22} />}
        title="No Radar run yet"
        message="Validate a Literature Radar result and ingest it manually with workbench-agent."
        action={<button type="button" onClick={() => void load()}>Reload</button>}
      />
    );
  }

  const profileName = recordText(run.profile, "name") ?? recordText(run.profile, "key") ?? "Literature Radar";
  const lookback = recordNumber(run.search_window, "lookback_days");
  const windowFrom = recordText(run.search_window, "from");
  const windowTo = recordText(run.search_window, "to");
  const zoteroSummary = recordText(run.zotero_context, "summary");

  return (
    <div className="radar-inbox">
      <section className="radar-run-card">
        <div className="radar-run-heading">
          <div>
            <span className="radar-eyebrow"><Sparkles size={13} />Latest Radar Run</span>
            <h2>{profileName}</h2>
            <p>
              Generated {formatDateTime(run.generated_at)}
              {lookback !== null ? ` · ${lookback}-day lookback` : ""}
              {windowFrom && windowTo ? ` · ${windowFrom} → ${windowTo}` : ""}
            </p>
          </div>
          <button className="radar-reload" type="button" onClick={() => void load()}>
            <RefreshCw size={14} />Reload persisted run
          </button>
        </div>

        <div className="radar-counts" aria-label="Radar run counts">
          <RunCount label="Candidates" value={run.candidate_count} />
          <RunCount label="Verified" value={run.verified_candidate_count} />
          <RunCount label="Recommended" value={run.recommended_count} emphasis />
        </div>

        <div className="radar-source-grid">
          {run.source_status.map((source) => (
            <article className={`radar-source radar-source-${source.status}`} key={source.name}>
              <div>
                <strong>{source.name}</strong>
                <span>{source.status.replace("_", " ")}</span>
              </div>
              <small>{source.result_count} results · {source.attempts} attempts</small>
              {source.warning ? <p>{source.warning}</p> : null}
            </article>
          ))}
        </div>

        {run.warnings.length > 0 ? (
          <div className="radar-warnings">
            <span><AlertTriangle size={14} />Run warnings</span>
            <ul>{run.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>
        ) : null}

        {zoteroSummary ? (
          <div className="radar-zotero-context">
            <span><BookOpenCheck size={14} />Zotero context</span>
            <p>{zoteroSummary}</p>
          </div>
        ) : null}
      </section>

      {reviewError ? (
        <div className="radar-inline-error">Review state could not be saved. Try again.</div>
      ) : null}

      <section className="radar-section">
        <div className="radar-section-heading">
          <div>
            <span>Priority reading list</span>
            <h2>Recommended Papers</h2>
          </div>
          <strong>{run.recommendations.length}</strong>
        </div>
        <div className="radar-paper-list">
          {run.recommendations.map((paper) => (
            <RadarPaperCard
              paper={paper}
              updating={updating === paper.recommendation_id}
              onReview={updateReview}
              key={paper.recommendation_id}
            />
          ))}
        </div>
      </section>

      <details className="radar-alternatives">
        <summary>
          <span>
            <strong>Verified Alternatives</strong>
            <small>Real and relevant papers that did not enter the Top {run.recommended_count}.</small>
          </span>
          <b>{run.verified_alternatives.length}</b>
        </summary>
        <div className="radar-paper-list radar-paper-list-alternatives">
          {run.verified_alternatives.map((paper) => (
            <RadarPaperCard
              paper={paper}
              updating={updating === paper.recommendation_id}
              onReview={updateReview}
              alternative
              key={paper.recommendation_id}
            />
          ))}
        </div>
      </details>

      <details className="radar-diagnostics">
        <summary>Run diagnostics and screening detail</summary>
        <pre>{JSON.stringify(run.diagnostics, null, 2)}</pre>
      </details>
    </div>
  );
}

function RadarPaperCard({
  paper,
  updating,
  alternative = false,
  onReview,
}: {
  paper: RadarPaper;
  updating: boolean;
  alternative?: boolean;
  onReview: (recommendationId: string, status: RadarReviewStatus) => Promise<void>;
}) {
  const relationship = paper.relationship_to_library
    ?? recordText(paper.zotero_relationship, "relationship_summary");
  const evidenceDepth = recordText(paper.evidence, "evidence_depth");
  const relatedPapers = recordList(paper.zotero_relationship, "related_papers");
  const primarySource = recordText(paper.evidence, "primary_url") ?? paper.url;

  return (
    <article className={`radar-paper${alternative ? " radar-paper-alternative" : ""}`}>
      <div className="radar-paper-topline">
        <div className="radar-paper-rank">
          {alternative ? "ALT" : `#${paper.selection_rank ?? "–"}`}
        </div>
        <div className="radar-paper-meta">
          {paper.venue ? <span>{paper.venue}</span> : null}
          {paper.publication_type ? <span>{paper.publication_type}</span> : null}
          {paper.published_at ? <time dateTime={paper.published_at}>{formatDate(paper.published_at)}</time> : null}
        </div>
        {paper.overall_score !== null ? (
          <strong className="radar-overall">Overall {formatScore(paper.overall_score)}</strong>
        ) : null}
      </div>

      <div className="radar-paper-title-row">
        <div>
          <h3>{paper.title}</h3>
          {paper.authors.length > 0 ? <p>{paper.authors.join(", ")}</p> : null}
        </div>
        <a href={primarySource} target="_blank" rel="noreferrer" aria-label={`Open primary source for ${paper.title}`}>
          <ExternalLink size={15} />Primary source
        </a>
      </div>

      {paper.ai_summary ? (
        <div className="radar-copy-block radar-summary-block">
          <span><Sparkles size={12} />AI Summary</span>
          <p>{paper.ai_summary}</p>
        </div>
      ) : null}
      <div className="radar-copy-block">
        <span>{alternative ? "Why it missed the Top list" : "Why Recommended"}</span>
        <p>{paper.recommendation_reason}</p>
      </div>
      {relationship ? (
        <div className="radar-copy-block radar-relationship-block">
          <span>Zotero Relationship</span>
          <p>{relationship}</p>
        </div>
      ) : null}

      <div className="radar-score-grid">
        <Score label="Relevance" value={paper.relevance_score} />
        <Score label="Novelty" value={paper.novelty_score} />
        <Score label="Scientific value" value={paper.scientific_value_score} />
        <Score label="Recency" value={paper.recency_score} />
        <Score label="Overall" value={paper.overall_score} emphasis />
      </div>

      <div className="radar-paper-footer">
        <div className="radar-evidence-line">
          {evidenceDepth ? <span>Evidence: {evidenceDepth.replace("_", " ")}</span> : null}
          {paper.doi ? <span>DOI {paper.doi}</span> : paper.arxiv_id ? <span>arXiv {paper.arxiv_id}</span> : null}
        </div>
        <label className={`radar-review radar-review-${paper.review_status}`}>
          <span>Review</span>
          <select
            value={paper.review_status}
            disabled={updating}
            onChange={(event) => void onReview(
              paper.recommendation_id,
              event.target.value as RadarReviewStatus,
            )}
          >
            {reviewOptions.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      {relatedPapers.length > 0 || Object.keys(paper.date_evidence).length > 0 ? (
        <details className="radar-paper-details">
          <summary>Evidence and library relationship detail</summary>
          {relatedPapers.length > 0 ? (
            <ul>
              {relatedPapers.map((item, index) => (
                <li key={`${recordText(item, "title") ?? "paper"}-${index}`}>
                  <strong>{recordText(item, "title") ?? "Related paper"}</strong>
                  {recordText(item, "relationship") ? ` — ${recordText(item, "relationship")}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
          <pre>{JSON.stringify(paper.date_evidence, null, 2)}</pre>
        </details>
      ) : null}
    </article>
  );
}

function RunCount({ label, value, emphasis = false }: { label: string; value: number; emphasis?: boolean }) {
  return (
    <div className={emphasis ? "radar-count radar-count-emphasis" : "radar-count"}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Score({ label, value, emphasis = false }: { label: string; value: number | null; emphasis?: boolean }) {
  return (
    <div className={emphasis ? "radar-score radar-score-emphasis" : "radar-score"}>
      <span>{label}</span>
      <strong>{value === null ? "–" : formatScore(value)}</strong>
    </div>
  );
}

function RadarState({
  icon,
  title,
  message,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="news-state radar-state">
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{message}</p>
      {action ? <div className="radar-state-action">{action}</div> : null}
    </div>
  );
}

function updateRunReview(run: RadarRun, response: RadarReviewResponse): RadarRun {
  const update = (paper: RadarPaper) => paper.recommendation_id === response.recommendation_id
    ? { ...paper, review_status: response.review_status }
    : paper;
  return {
    ...run,
    recommendations: run.recommendations.map(update),
    verified_alternatives: run.verified_alternatives.map(update),
  };
}

function recordText(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value ? value : null;
}

function recordNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" ? value : null;
}

function recordList(record: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = record[key];
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => (
      typeof item === "object" && item !== null && !Array.isArray(item)
    ))
    : [];
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}
