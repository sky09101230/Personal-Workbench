import { Bot, Clipboard, RefreshCw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, getJson, postJson } from "../api";
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
      setError("Enter a question about the selected text first.");
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
    return <AssistantState icon={<RefreshCw size={18} className="spin" />} title="Loading AI history" detail="Reading saved analyses and paper conversation." />;
  }

  return (
    <div className="ai-assistant">
      {error ? (
        <div className="ai-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      ) : null}

      <AssistantSection title="Overview">
        {overview ? (
          <ResultCard analysis={overview} pending={pending} onAdd={() => addAnalysisToNotes(overview)} onRetry={() => generateAnalysis("overview", true)} />
        ) : (
          <TriggerButton pending={pending === "overview"} label="Generate Overview" onClick={() => generateAnalysis("overview")} />
        )}
      </AssistantSection>

      <AssistantSection title="Deep Read">
        {deepRead ? (
          <ResultCard analysis={deepRead} pending={pending} onAdd={() => addAnalysisToNotes(deepRead)} onRetry={() => generateAnalysis("deep_read", true)} />
        ) : (
          <TriggerButton pending={pending === "deep_read"} label="Run Deep Read" onClick={() => generateAnalysis("deep_read")} />
        )}
      </AssistantSection>

      <AssistantSection title="Ask Paper">
        <div className="ai-messages">
          {messages.length > 0 ? messages.map((message) => (
            <article className={`ai-message ${message.role}`} key={message.id}>
              <span>{message.role === "assistant" ? "AI" : "You"}</span>
              <p>{messageText(message)}</p>
              {message.role === "assistant" ? (
                <ResultActions
                  content={formatContent(message.content)}
                  disabled={pending !== null}
                  onAdd={() => addMessageToNotes(message)}
                />
              ) : null}
            </article>
          )) : <p className="ai-muted">No questions yet. Answers stay bound to this paper.</p>}
        </div>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about this paper…" rows={3} />
        <TriggerButton pending={pending === "ask-paper"} label="Ask Paper" disabled={!question.trim()} onClick={askPaper} />
      </AssistantSection>

      <AssistantSection title="Selected Text">
        {selection ? (
          <>
            <blockquote className="selection-preview">{selection.selectedText}</blockquote>
            <div className="selection-actions">
              {(["explain", "summarize", "translate"] as SelectionAction[]).map((action) => (
                <button type="button" key={action} disabled={pending !== null} onClick={() => runSelection(action)}>{selectionActionLabel(action)}</button>
              ))}
            </div>
            <input value={selectionQuestion} onChange={(event) => setSelectionQuestion(event.target.value)} placeholder="Question about selection" />
            <TriggerButton pending={pending === "selection-ask"} label="Ask AI" disabled={!selectionQuestion.trim()} onClick={() => runSelection("ask")} />
          </>
        ) : <p className="ai-muted">Select text on the current PDF page to enable focused actions.</p>}
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
      <button type="button" disabled={disabled} onClick={() => void copy()}><Clipboard size={13} />{copied ? "Copied" : "Copy"}</button>
      <button type="button" disabled={disabled} onClick={onAdd}><Save size={13} />Add to Notes</button>
      {onRetry ? <button type="button" disabled={disabled} onClick={onRetry}><RefreshCw size={13} />Retry</button> : null}
    </div>
  );
}

function TriggerButton({ pending, label, disabled = false, onClick }: { pending: boolean; label: string; disabled?: boolean; onClick: () => void }) {
  return <button className="ai-trigger" type="button" disabled={disabled || pending} onClick={onClick}>{pending ? <RefreshCw size={14} className="spin" /> : <Bot size={14} />}{pending ? "Working…" : label}</button>;
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
  if (action === "explain") return "Explain";
  if (action === "summarize") return "Summarize";
  if (action === "translate") return "Translate";
  return "Ask AI";
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "AI request failed. Please retry.";
}
