import { Check, Circle, Save, Star, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Project, TaskPatch, TaskPriority, TodoTask } from "../types";

type TaskCardProps = {
  task: TodoTask;
  projects: Project[];
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
};

export function TaskCard({ task, projects, onPatch, onDelete }: TaskCardProps) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setTitle(task.title);
    setDescription(task.description ?? "");
  }, [task.description, task.title]);

  const mutate = async (patch: TaskPatch) => {
    setSaving(true);
    try {
      await onPatch(task.id, patch);
    } finally {
      setSaving(false);
    }
  };

  const saveText = () => mutate({ title, description: description || null });
  const project = projects.find((item) => item.id === task.project_id);
  const finished = task.status === "done" || task.status === "cancelled";

  return (
    <article className={`todo-task-card${finished ? " finished" : ""}`}>
      <button
        className="todo-complete"
        type="button"
        title={task.status === "done" ? "Reopen task" : "Complete task"}
        onClick={() => void mutate({ status: task.status === "done" ? "todo" : "done" })}
        disabled={saving || task.status === "cancelled"}
      >
        {task.status === "done" ? <Check size={15} /> : <Circle size={15} />}
      </button>
      <div className="todo-task-body">
        <div className="todo-task-title-row">
          <input
            aria-label="Task title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            disabled={saving}
          />
          {task.is_next_action ? <span className="next-badge"><Star size={11} /> Next</span> : null}
        </div>
        <textarea
          aria-label="Task description"
          placeholder="Optional notes"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={saving}
        />
        <div className="todo-task-fields">
          <label>
            <span>Project</span>
            <select
              value={task.project_id ?? ""}
              onChange={(event) => void mutate({ project_id: event.target.value || null })}
              disabled={saving}
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
              onChange={(event) => void mutate({ planned_date: event.target.value || null })}
              disabled={saving}
            />
          </label>
          <label>
            <span>Due</span>
            <input
              type="date"
              value={task.due_date ?? ""}
              onChange={(event) => void mutate({ due_date: event.target.value || null })}
              disabled={saving}
            />
          </label>
          <label>
            <span>Priority</span>
            <select
              value={task.priority ?? ""}
              onChange={(event) => void mutate({
                priority: (event.target.value || null) as TaskPriority | null,
              })}
              disabled={saving}
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
            <button type="button" onClick={() => void saveText()} disabled={saving || !title.trim()}>
              <Save size={13} /> Save
            </button>
            {!finished && task.project_id ? (
              <button
                className={task.is_next_action ? "active" : ""}
                type="button"
                onClick={() => void mutate({ is_next_action: !task.is_next_action })}
                disabled={saving}
              >
                <Star size={13} /> {task.is_next_action ? "Next action" : "Make next"}
              </button>
            ) : null}
            {!finished ? (
              <button type="button" onClick={() => void mutate({ status: "cancelled" })} disabled={saving}>
                <X size={13} /> Cancel
              </button>
            ) : null}
            <button
              className="danger"
              type="button"
              onClick={() => {
                if (window.confirm(`Delete “${task.title}”?`)) void onDelete(task.id);
              }}
              disabled={saving}
            >
              <Trash2 size={13} /> Delete
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
