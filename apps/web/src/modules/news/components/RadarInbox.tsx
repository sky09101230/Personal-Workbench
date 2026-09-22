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
import { ApiError, postJson } from "../../../core/api";
import type {
  RadarLatestResponse,
  RadarPaper,
  RadarReviewResponse,
  RadarReviewStatus,
  RadarRun,
  RadarSourceStatus,
} from "../types";

const reviewOptions: { label: string; value: RadarReviewStatus }[] = [
  { label: "未查看", value: "new" },
  { label: "已查看", value: "seen" },
  { label: "感兴趣", value: "interested" },
  { label: "已忽略", value: "dismissed" },
];

export function RadarInbox() {
  const [run, setRun] = useState<RadarRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState(false);
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await getNewsJson<RadarLatestResponse>(
        "/api/news/papers/research/radar/latest",
      );
      setRun(response.run);
      if (response.run) {
        const ids = [...response.run.recommendations, ...response.run.verified_alternatives].map((p) => p.recommendation_id);
        try {
          const state = await postJson<{ saved: Record<string, string> }>("/api/literature/imports/radar-saved", { recommendation_ids: ids });
          setSaved(state.saved);
          setSaveError("");
        } catch { setSaveError("无法读取入库状态，仍可审核雷达结果。"); }
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const savePaper = async (id: string) => {
    setSaving(id);
    setSaveError("");
    try {
      const result = await postJson<{ paper_id: string }>(`/api/literature/imports/radar/${encodeURIComponent(id)}`);
      setSaved((current) => ({ ...current, [id]: result.paper_id }));
    } catch (error) {
      setSaveError(error instanceof ApiError && error.code === "identity_conflict" ? "文献标识存在冲突，未执行合并。请核对来源元数据后再保存。" : "无法保存到文献库，请重试。");
    } finally { setSaving(null); }
  };

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
        title="正在加载发现雷达"
        message="正在读取最近一次已验证的文献发现结果。"
      />
    );
  }
  if (error) {
    return (
      <RadarState
        icon={<AlertCircle size={22} />}
        title="发现雷达暂不可用"
        message="无法读取 Workbench 保存的雷达结果。"
        action={<button type="button" onClick={() => void load()}>重试</button>}
      />
    );
  }
  if (!run) {
    return (
      <RadarState
        icon={<Sparkles size={22} />}
        title="暂无雷达结果"
        message="请先验证并导入一次文献雷达结果。"
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
            <span className="radar-eyebrow"><Sparkles size={13} />最近一次发现</span>
            <h2>{profileName}</h2>
            <p>
              生成时间：{formatDateTime(run.generated_at)}
              {lookback !== null ? ` · ${lookback} 天回溯` : ""}
              {windowFrom && windowTo ? ` · ${windowFrom} → ${windowTo}` : ""}
            </p>
          </div>
          <button className="radar-reload" type="button" onClick={() => void load()}>
            <RefreshCw size={14} />刷新发现结果
          </button>
        </div>

        <div className="radar-counts" aria-label="雷达结果统计">
          <RunCount label="候选文献" value={run.candidate_count} />
          <RunCount label="已验证" value={run.verified_candidate_count} />
          <RunCount label="推荐" value={run.recommended_count} emphasis />
        </div>

        <div className="radar-source-grid">
          {run.source_status.map((source) => (
            <SourceStatusCard source={source} key={source.name} />
          ))}
        </div>

        {run.warnings.length > 0 ? (
          <div className="radar-warnings">
            <span><AlertTriangle size={14} />运行提示</span>
            <ul>{run.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>
        ) : null}

        {zoteroSummary ? (
          <div className="radar-zotero-context">
            <span><BookOpenCheck size={14} />Zotero 参考背景</span>
            <p>{zoteroSummary}</p>
          </div>
        ) : null}
      </section>

      {reviewError ? (
        <div className="radar-inline-error">审核状态保存失败，请重试。</div>
      ) : null}
      {saveError ? <div className="radar-inline-error" role="alert">{saveError}</div> : null}

      <section className="radar-section">
        <div className="radar-section-heading">
          <div>
            <span>优先阅读列表</span>
            <h2>推荐论文</h2>
          </div>
          <strong>{run.recommendations.length}</strong>
        </div>
        <div className="radar-paper-list">
          {run.recommendations.map((paper) => (
            <RadarPaperCard
              paper={paper}
              updating={updating === paper.recommendation_id}
              onReview={updateReview}
              savedId={saved[paper.recommendation_id]}
              saving={saving === paper.recommendation_id}
              onSave={savePaper}
              key={paper.recommendation_id}
            />
          ))}
        </div>
      </section>

      <details className="radar-alternatives">
        <summary>
          <span>
            <strong>已验证的备选论文</strong>
            <small>真实且相关、但未进入前 {run.recommended_count} 名的论文。</small>
          </span>
          <b>{run.verified_alternatives.length}</b>
        </summary>
        <div className="radar-paper-list radar-paper-list-alternatives">
          {run.verified_alternatives.map((paper) => (
            <RadarPaperCard
              paper={paper}
              updating={updating === paper.recommendation_id}
              onReview={updateReview}
              savedId={saved[paper.recommendation_id]}
              saving={saving === paper.recommendation_id}
              onSave={savePaper}
              alternative
              key={paper.recommendation_id}
            />
          ))}
        </div>
      </details>

      <details className="radar-diagnostics">
        <summary>运行诊断与筛选详情</summary>
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
  savedId,
  saving,
  onSave,
}: {
  paper: RadarPaper;
  updating: boolean;
  alternative?: boolean;
  onReview: (recommendationId: string, status: RadarReviewStatus) => Promise<void>;
  savedId?: string;
  saving: boolean;
  onSave: (id: string) => Promise<void>;
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
          <strong className="radar-overall">综合评分 {formatScore(paper.overall_score)}</strong>
        ) : null}
      </div>

      <div className="radar-paper-title-row">
        <div>
          <h3>{paper.title}</h3>
          {paper.authors.length > 0 ? <p>{paper.authors.join(", ")}</p> : null}
        </div>
        <a href={primarySource} target="_blank" rel="noreferrer" aria-label={`打开论文原始来源：${paper.title}`}>
          <ExternalLink size={15} />原始来源
        </a>
      </div>

      {paper.ai_summary ? (
        <div className="radar-copy-block radar-summary-block">
          <span><Sparkles size={12} />AI 摘要</span>
          <p>{paper.ai_summary}</p>
        </div>
      ) : null}
      <div className="radar-copy-block">
        <span>{alternative ? "未进入推荐列表的原因" : "推荐理由"}</span>
        <p>{paper.recommendation_reason}</p>
      </div>
      {relationship ? (
        <div className="radar-copy-block radar-relationship-block">
          <span>与 Zotero 文献的关系</span>
          <p>{relationship}</p>
        </div>
      ) : null}

      <div className="radar-score-grid">
        <Score label="相关性" value={paper.relevance_score} />
        <Score label="新颖性" value={paper.novelty_score} />
        <Score label="科学价值" value={paper.scientific_value_score} />
        <Score label="时效性" value={paper.recency_score} />
        <Score label="综合评分" value={paper.overall_score} emphasis />
      </div>

      <div className="radar-paper-footer">
        {savedId ? <a className="library-save" href={`/literature?paper=${encodeURIComponent(savedId)}`}>已入库 · 打开文献</a> : <button className="library-save" type="button" disabled={saving} onClick={() => void onSave(paper.recommendation_id)}>{saving ? "正在保存…" : "保存到文献库"}</button>}
        <div className="radar-evidence-line">
          {evidenceDepth ? <span>依据：{evidenceDepth.replace("_", " ")}</span> : null}
          {paper.doi ? <span>DOI {paper.doi}</span> : paper.arxiv_id ? <span>arXiv {paper.arxiv_id}</span> : null}
        </div>
        <label className={`radar-review radar-review-${paper.review_status}`}>
          <span>审核状态</span>
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
          <summary>依据与文献库关联详情</summary>
          {relatedPapers.length > 0 ? (
            <ul>
              {relatedPapers.map((item, index) => (
                <li key={`${recordText(item, "title") ?? "paper"}-${index}`}>
                  <strong>{recordText(item, "title") ?? "关联文献"}</strong>
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

function SourceStatusCard({ source }: { source: RadarSourceStatus }) {
  const note = sourceStatusNote(source);
  return (
    <article className={`radar-source radar-source-${source.status}`}>
      <div className="radar-source-heading">
        <strong>{source.name}</strong>
        <span>{source.status.replace("_", " ")}</span>
      </div>
      <small>{source.result_count} 条结果 · {source.attempts} 次尝试</small>
      {note ? <p className="radar-source-note">{note}</p> : null}
      {source.routes.length > 0 || source.warning ? (
        <details className="radar-source-details">
          <summary>访问路径与环境详情</summary>
          {source.warning ? <p>{source.warning}</p> : null}
          {source.routes.length > 0 ? (
            <ul>
              {source.routes.map((route, index) => (
                <li key={`${recordText(route, "route") ?? "route"}-${index}`}>
                  <strong>{recordText(route, "route") ?? `route ${index + 1}`}</strong>
                  <span>{recordText(route, "status") ?? "diagnostic"}</span>
                  {safeRouteDetail(route) ? <small>{safeRouteDetail(route)}</small> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </details>
      ) : null}
    </article>
  );
}


function sourceStatusNote(source: RadarSourceStatus): string | null {
  if (source.status === "degraded" && source.result_count > 0) {
    return "已有可用依据，部分访问路径受限。";
  }
  if (source.status === "degraded") {
    return "此来源受限，可用依据由其他来源提供。";
  }
  if (source.status === "failed") return "未从此来源获得可用依据。";
  if (source.status === "not_attempted") return "本次未访问此来源。";
  return null;
}


function safeRouteDetail(route: Record<string, unknown>): string {
  return Object.entries(route)
    .filter(([key]) => !["route", "status"].includes(key))
    .filter(([key]) => !/(?:api[_-]?key|token|authorization|headers?)/i.test(key))
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${formatDiagnosticValue(value)}`)
    .join(" · ");
}


function formatDiagnosticValue(value: unknown): string {
  if (value === null) return "none";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return JSON.stringify(value);
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
