import { Bot, Clipboard, RefreshCw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { getJson, postJson, workflowError } from "../api";
import type {
  AnalysisListResponse,
  ConversationListResponse,
  LiteratureAIAnalysis,
  LiteratureAIConversation,
  LiteratureAIMessage,
  MessageListResponse,
  PdfSelection,
  LiteratureUserNote,
} from "../types";

type SelectionAction = "explain" | "summarize" | "translate" | "ask";

export function LiteratureAIAssistant({
  paperId,
  selection,
  onNoteAdded,
}: {
  paperId: string;
  selection: PdfSelection | null;
  onNoteAdded: (note: LiteratureUserNote) => void;
}) {
  const encodedPaperId = encodeURIComponent(paperId);
  const [analyses, setAnalyses] = useState<LiteratureAIAnalysis[]>([]);
  const [conversation, setConversation] = useState<LiteratureAIConversation | null>(null);
  const [messages, setMessages] = useState<LiteratureAIMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [selectionQuestion, setSelectionQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAnalyses([]);
    setConversation(null);
    setMessages([]);
    setQuestion("");
    Promise.all([
      getJson<AnalysisListResponse>(`/api/literature/papers/${encodedPaperId}/ai/analyses`),
      getJson<ConversationListResponse>(`/api/literature/papers/${encodedPaperId}/ai/conversations`),
    ])
      .then(async ([analysisResponse, conversationResponse]) => {
        if (cancelled) return;
        setAnalyses(analysisResponse.items);
        const latest = conversationResponse.items[0] ?? null;
        setConversation(latest);
        if (latest) {
          const messageResponse = await getJson<MessageListResponse>(
            `/api/literature/papers/${encodedPaperId}/ai/conversations/${encodeURIComponent(latest.id)}/messages`,
          );
          if (!cancelled) setMessages(messageResponse.items);
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(errorMessage(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [encodedPaperId]);

  const overview = useMemo(
    () => analyses.find((analysis) => analysis.analysis_type === "overview") ?? null,
    [analyses],
  );
  const deepRead = useMemo(
    () => analyses.find((analysis) => analysis.analysis_type === "deep_read") ?? null,
    [analyses],
  );
  const latestSelection = useMemo(
    () => analyses.find((analysis) => analysis.analysis_type.startsWith("selection_")) ?? null,
    [analyses],
  );

  const generateAnalysis = async (analysisType: "overview" | "deep_read", regenerate = false) => {
    setPending(analysisType);
    setError(null);
    try {
      const analysis = await postJson<LiteratureAIAnalysis>(
        `/api/literature/papers/${encodedPaperId}/ai/analyses`,
        { analysis_type: analysisType, regenerate },
      );
      setAnalyses((items) => [analysis, ...items.filter((item) => item.id !== analysis.id)]);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPending(null);
    }
  };

  const askPaper = async () => {
    const text = question.trim();
    if (!text) return;
    setPending("ask-paper");
    setError(null);
    try {
      let target = conversation;
      if (!target) {
        target = await postJson<LiteratureAIConversation>(
          `/api/literature/papers/${encodedPaperId}/ai/conversations`,
        );
        setConversation(target);
      }
      const response = await postJson<MessageListResponse>(
        `/api/literature/papers/${encodedPaperId}/ai/conversations/${encodeURIComponent(target.id)}/messages`,
        { question: text },
      );
      setMessages((items) => [...items, ...response.items]);
      setQuestion("");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPending(null);
    }
  };

  const runSelection = async (action: SelectionAction) => {
    if (!selection) return;
    if (action === "ask" && !selectionQuestion.trim()) {
      setError("请先输入关于选中文本的问题。");
      return;
    }
    setPending(`selection-${action}`);
    setError(null);
    try {
      const analysis = await postJson<LiteratureAIAnalysis>(
        `/api/literature/papers/${encodedPaperId}/ai/selection`,
        {
          action,
          page_number: selection.pageNumber,
          selected_text: selection.selectedText,
          context_before: selection.contextBefore,
          context_after: selection.contextAfter,
          question: action === "ask" ? selectionQuestion.trim() : undefined,
        },
      );
      setAnalyses((items) => [analysis, ...items]);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPending(null);
    }
  };

  const addAnalysisToNotes = async (analysis: LiteratureAIAnalysis) => {
    await addToNotes({ analysis_id: analysis.id }, analysis.id);
  };

  const addMessageToNotes = async (message: LiteratureAIMessage) => {
    await addToNotes({ message_id: message.id }, message.id);
  };

  const addToNotes = async (body: object, key: string) => {
    setPending(`note-${key}`);
    setError(null);
    try {
      const note = await postJson<LiteratureUserNote>(
        `/api/literature/papers/${encodedPaperId}/user-notes`,
        body,
      );
      onNoteAdded(note);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPending(null);
    }
  };

  if (loading) {
    return <AssistantState icon={<RefreshCw size={18} className="spin" />} title="正在加载 AI 历史" detail="正在读取已保存的分析和论文对话。" />;
  }

  return (
    <div className="ai-assistant">
      {error ? (
        <div className="ai-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>关闭</button>
        </div>
      ) : null}

      <AssistantSection title="概览">
        {overview ? (
          <ResultCard analysis={overview} pending={pending} onAdd={() => addAnalysisToNotes(overview)} onRetry={() => generateAnalysis("overview", true)} />
        ) : (
          <TriggerButton pending={pending === "overview"} label="生成概览" onClick={() => generateAnalysis("overview")} />
        )}
      </AssistantSection>

      <AssistantSection title="精读">
        {deepRead ? (
          <ResultCard analysis={deepRead} pending={pending} onAdd={() => addAnalysisToNotes(deepRead)} onRetry={() => generateAnalysis("deep_read", true)} />
        ) : (
          <TriggerButton pending={pending === "deep_read"} label="开始精读" onClick={() => generateAnalysis("deep_read")} />
        )}
      </AssistantSection>

      <AssistantSection title="论文问答">
        <div className="ai-messages">
          {messages.length > 0 ? messages.map((message) => (
            <article className={`ai-message ${message.role}`} key={message.id}>
              <span>{message.role === "assistant" ? "AI" : "你"}</span>
              <p>{messageText(message)}</p>
              {message.role === "assistant" ? (
                <ResultActions
                  content={formatContent(message.content)}
                  disabled={pending !== null}
                  onAdd={() => addMessageToNotes(message)}
                />
              ) : null}
            </article>
          )) : <p className="ai-muted">暂无提问。对话始终与此论文关联。</p>}
        </div>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="就这篇论文提问…" rows={3} />
        <TriggerButton pending={pending === "ask-paper"} label="论文问答" disabled={!question.trim()} onClick={askPaper} />
      </AssistantSection>

      <AssistantSection title="选中文本">
        {selection ? (
          <>
            <blockquote className="selection-preview">{selection.selectedText}</blockquote>
            <div className="selection-actions">
              {(["explain", "summarize", "translate"] as SelectionAction[]).map((action) => (
                <button type="button" key={action} disabled={pending !== null} onClick={() => runSelection(action)}>{selectionActionLabel(action)}</button>
              ))}
            </div>
            <input value={selectionQuestion} onChange={(event) => setSelectionQuestion(event.target.value)} placeholder="关于选中文本的问题" />
            <TriggerButton pending={pending === "selection-ask"} label="向 AI 提问" disabled={!selectionQuestion.trim()} onClick={() => runSelection("ask")} />
          </>
        ) : <p className="ai-muted">在当前 PDF 页选中文本后，可解释、总结或提问。</p>}
        {latestSelection ? (
          <ResultCard analysis={latestSelection} pending={pending} onAdd={() => addAnalysisToNotes(latestSelection)} />
        ) : null}
      </AssistantSection>
    </div>
  );
}

function AssistantSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="ai-section"><h3>{title}</h3>{children}</section>;
}

function ResultCard({
  analysis,
  pending,
  onAdd,
  onRetry,
}: {
  analysis: LiteratureAIAnalysis;
  pending: string | null;
  onAdd: () => void;
  onRetry?: () => void;
}) {
  const content = formatContent(analysis.content);
  return (
    <article className="ai-result-card">
      <div className="ai-result-meta"><span>{analysis.model}</span><span>{analysis.prompt_version}</span></div>
      <pre>{content}</pre>
      <ResultActions content={content} disabled={pending !== null} onAdd={onAdd} onRetry={onRetry} />
    </article>
  );
}

function ResultActions({ content, disabled, onAdd, onRetry }: { content: string; disabled: boolean; onAdd: () => void; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="ai-result-actions">
      <button type="button" disabled={disabled} onClick={() => void copy()}><Clipboard size={13} />{copied ? "已复制" : "复制"}</button>
      <button type="button" disabled={disabled} onClick={onAdd}><Save size={13} />保存到笔记</button>
      {onRetry ? <button type="button" disabled={disabled} onClick={onRetry}><RefreshCw size={13} />重试</button> : null}
    </div>
  );
}

function TriggerButton({ pending, label, disabled = false, onClick }: { pending: boolean; label: string; disabled?: boolean; onClick: () => void }) {
  return <button className="ai-trigger" type="button" disabled={disabled || pending} onClick={onClick}>{pending ? <RefreshCw size={14} className="spin" /> : <Bot size={14} />}{pending ? "正在处理…" : label}</button>;
}

function AssistantState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="reader-state">{icon}<strong>{title}</strong><p>{detail}</p></div>;
}

function messageText(message: LiteratureAIMessage) {
  if (message.role === "user") {
    return "question" in message.content ? message.content.question : "";
  }
  return formatContent(message.content);
}

function formatContent(content: object) {
  return Object.entries(content).map(([key, value]) => {
    const label = key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
    if (Array.isArray(value)) return `${label}:\n${value.map((item) => `• ${String(item)}`).join("\n")}`;
    return `${label}: ${String(value)}`;
  }).join("\n\n");
}

function selectionActionLabel(action: SelectionAction) {
  if (action === "explain") return "解释";
  if (action === "summarize") return "总结";
  if (action === "translate") return "翻译";
  return "向 AI 提问";
}

function errorMessage(error: unknown) {
  return workflowError(error);
}
