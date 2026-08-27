import {
  CalendarCheck,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  FileText,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Project, TaskPatch, TaskPriority, TodoTask } from "../types";

type TaskCardProps = {
  task: TodoTask;
  projects: Project[];
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
  onRescheduleToday?: (taskId: string) => Promise<void>;
};

const priorityLabels: Record<TaskPriority, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

function shortDate(isoDate: string): string {
  return isoDate.slice(5);
}

export function TaskCard({ task, projects, onPatch, onDelete, onRescheduleToday }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  // Expanded-editor drafts re-seed only when the panel opens; reconciliation
  // replaces the task object in place and must not clobber in-progress typing.
  const [titleDraft, setTitleDraft] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState("");

  useEffect(() => {
    if (expanded) {
      setTitleDraft(task.title);
      setDescriptionDraft(task.description ?? "");
    }
    // Re-seed deliberately on expand toggle only, not on every task object change.
  }, [expanded]);

  const [pendingField, setPendingField] = useState<string | null>(null);

  const patchWithPending = async (field: string, patch: TaskPatch) => {
    setPendingField(field);
    try {
      await onPatch(task.id, patch);
    } finally {
      setPendingField(null);
    }
  };

  const project = projects.find((item) => item.id === task.project_id);
  const finished = task.status === "done" || task.status === "cancelled";

  const commitTitle = () => {
    const title = titleDraft.trim();
    if (!title) {
      setTitleDraft(task.title);
      return;
    }
    if (title !== task.title) void patchWithPending("title", { title });
  };
  const commitDescription = () => {
    const description = descriptionDraft.trim() || null;
    if (description !== task.description) {
      void patchWithPending("description", { description });
    }
  };
  const hasNotes = Boolean(task.description);
  const busy = pendingField !== null;

  return (
    <article className={`todo-task-card${finished ? " finished" : ""}`}>
      <div
        className="todo-task-row"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={(event) => {
          if ((event.target as HTMLElement).closest("button, input, select, textarea")) return;
          setExpanded((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && event.currentTarget === event.target) {
            setExpanded((value) => !value);
          }
        }}
      >
        <button
          className="todo-complete"
          type="button"
          title={task.status === "done" ? "Reopen task" : "Complete task"}
          onClick={() => void patchWithPending("status", { status: task.status === "done" ? "todo" : "done" })}
          disabled={pendingField === "status" || task.status === "cancelled"}
        >
          {task.status === "done" ? <Check size={15} /> : <Circle size={15} />}
        </button>
        <span className="todo-row-title">{task.title}</span>
        {task.is_next_action ? <span className="next-badge"><Star size={11} /> Next</span> : null}
        {hasNotes ? <FileText size={13} className="row-notes-icon" aria-label="Has notes" /> : null}
        {task.planned_date ? (
          <span className="todo-meta-chip">计划 {shortDate(task.planned_date)}</span>
        ) : null}
        {task.due_date ? (
          <span className="todo-meta-chip">截止 {shortDate(task.due_date)}</span>
        ) : null}
        {task.priority ? (
          <span className={`todo-meta-chip pri-${task.priority}`}>{priorityLabels[task.priority]}</span>
        ) : null}
        {project ? <span className="todo-meta-chip">{project.name}</span> : null}
        {!finished && onRescheduleToday ? (
          <button
            className={`quick-today${pendingField === "reschedule" ? " busy" : ""}`}
            type="button"
            title="Schedule to today"
            onClick={() => {
              setPendingField("reschedule");
              onRescheduleToday(task.id).finally(() => setPendingField(null));
            }}
            disabled={busy && pendingField === "reschedule"}
          >
            <CalendarCheck size={12} /> 今天
          </button>
        ) : null}
        <button
          className="todo-expand"
          type="button"
          aria-label={expanded ? "Collapse task editor" : "Expand task editor"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {expanded ? (
        <div className="todo-task-editor">
          <div className="todo-task-title-row">
            <input
              aria-label="Task title"
              value={titleDraft}
              onChange={(event) => setTitleDraft(event.target.value)}
              onBlur={commitTitle}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  event.currentTarget.blur();
                }
                if (event.key === "Escape") {
                  setTitleDraft(task.title);
                  event.currentTarget.blur();
                }
              }}
              disabled={pendingField === "title"}
            />
          </div>
          <textarea
            aria-label="Task description"
            placeholder="Optional notes"
            value={descriptionDraft}
            onChange={(event) => setDescriptionDraft(event.target.value)}
            onBlur={commitDescription}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setDescriptionDraft(task.description ?? "");
                event.currentTarget.blur();
              }
            }}
            disabled={pendingField === "description"}
          />
          <div className="todo-task-fields">
            <label>
              <span>Project</span>
              <select
                value={task.project_id ?? ""}
                onChange={(event) =>
                  void patchWithPending("project_id", { project_id: event.target.value || null })
                }
                disabled={pendingField === "project_id"}
              >
                <option value="">Inbox</option>
                {projects.filter((item) => item.status !== "archived").map((item) => (
                  <option value={item.id} key={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Plan</span>
              <input
                type="date"
                value={task.planned_date ?? ""}
                onChange={(event) => void patchWithPending("planned_date", { planned_date: event.target.value || null })}
                disabled={pendingField === "planned_date"}
              />
            </label>
            <label>
              <span>Due</span>
              <input
                type="date"
                value={task.due_date ?? ""}
                onChange={(event) => void patchWithPending("due_date", { due_date: event.target.value || null })}
                disabled={pendingField === "due_date"}
              />
            </label>
            <label>
              <span>Priority</span>
              <select
                value={task.priority ?? ""}
                onChange={(event) => void patchWithPending("priority", {
                  priority: (event.target.value || null) as TaskPriority | null,
                })}
                disabled={pendingField === "priority"}
              >
                <option value="">None</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
          </div>
          <div className="todo-task-footer">
            <span>{project?.name ?? "Inbox"} · {task.status}</span>
            <div>
              {!finished && task.project_id ? (
                <button
                  className={task.is_next_action ? "active" : ""}
                  type="button"
                  onClick={() => void patchWithPending("is_next_action", { is_next_action: !task.is_next_action })}
                  disabled={pendingField === "is_next_action"}
                >
                  <Star size={13} /> {task.is_next_action ? "Next action" : "Make next"}
                </button>
              ) : null}
              {!finished ? (
                <button
                  type="button"
                  onClick={() => void patchWithPending("status", { status: "cancelled" })}
                  disabled={pendingField === "status"}
                >
                  <X size={13} /> Cancel
                </button>
              ) : null}
              <button
                className="danger"
                type="button"
                onClick={() => {
                  if (window.confirm(`Delete “${task.title}”?`)) {
                    setPendingField("delete");
                    onDelete(task.id).finally(() => setPendingField(null));
                  }
                }}
                disabled={busy}
              >
                <Trash2 size={13} /> Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}
