import {
  AlertCircle,
  Archive,
  CalendarDays,
  CheckCircle2,
  Inbox,
  ListTodo,
  LoaderCircle,
  Plus,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { deleteTodo, getTodoJson, patchTodoJson, postTodoJson, TodoApiError } from "./api";
import { TaskCard } from "./components/TaskCard";
import type {
  ItemList,
  PlanProposal,
  Project,
  ProjectDetail,
  ProjectStatus,
  TaskPatch,
  TodoTask,
  TodayView,
} from "./types";
import "./todo.css";

type TodoView = "today" | "inbox" | "projects" | "upcoming" | "completed";

const views: { id: TodoView; label: string; icon: typeof CalendarDays }[] = [
  { id: "today", label: "Today", icon: CalendarDays },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "projects", label: "Projects", icon: ListTodo },
  { id: "upcoming", label: "Upcoming", icon: Archive },
  { id: "completed", label: "Completed", icon: CheckCircle2 },
];

export function TodoPage() {
  const [activeView, setActiveView] = useState<TodoView>("today");
  const [projects, setProjects] = useState<Project[]>([]);
  const [allTasks, setAllTasks] = useState<TodoTask[]>([]);
  const [today, setToday] = useState<TodayView | null>(null);
  const [items, setItems] = useState<TodoTask[]>([]);
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [captureTitle, setCaptureTitle] = useState("");
  const [captureProjectId, setCaptureProjectId] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [projectTaskTitle, setProjectTaskTitle] = useState("");
  const [proposal, setProposal] = useState<PlanProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBase = useCallback(async () => {
    const [projectResult, taskResult] = await Promise.all([
      getTodoJson<ItemList<Project>>("/api/todo/projects"),
      getTodoJson<ItemList<TodoTask>>("/api/todo/tasks"),
    ]);
    setProjects(projectResult.items);
    setAllTasks(taskResult.items);
    setSelectedProjectId((current) => current || projectResult.items.find((p) => p.status === "active")?.id || "");
  }, []);

  const loadView = useCallback(async () => {
    if (activeView === "today") {
      setToday(await getTodoJson<TodayView>("/api/todo/today"));
      return;
    }
    if (activeView === "projects") {
      if (selectedProjectId) {
        setProjectDetail(await getTodoJson<ProjectDetail>(`/api/todo/projects/${selectedProjectId}/detail`));
      } else {
        setProjectDetail(null);
      }
      return;
    }
    const endpoint = activeView === "inbox" ? "inbox" : activeView;
    setItems((await getTodoJson<ItemList<TodoTask>>(`/api/todo/${endpoint}`)).items);
  }, [activeView, selectedProjectId]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      await loadBase();
      await loadView();
    } catch (requestError) {
      setError(messageForError(requestError));
    }
  }, [loadBase, loadView]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    void Promise.all([loadBase(), loadView()])
      .catch((requestError) => setError(messageForError(requestError)))
      .finally(() => setLoading(false));
  }, [loadBase, loadView]);

  const mutate = async (operation: () => Promise<unknown>) => {
    setMutating(true);
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (requestError) {
      setError(messageForError(requestError));
    } finally {
      setMutating(false);
    }
  };

  const capture = async () => {
    const title = captureTitle.trim();
    if (!title) return;
    await mutate(async () => {
      await postTodoJson<TodoTask>("/api/todo/tasks", {
        title,
        project_id: captureProjectId || null,
      });
      setCaptureTitle("");
    });
  };

  const patchTask = (taskId: string, patch: TaskPatch) =>
    mutate(() => patchTodoJson<TodoTask>(`/api/todo/tasks/${taskId}`, patch));
  const deleteTask = (taskId: string) => mutate(() => deleteTodo(`/api/todo/tasks/${taskId}`));

  const taskNames = useMemo(
    () => Object.fromEntries(allTasks.map((task) => [task.id, task.title])),
    [allTasks],
  );
  const currentView = views.find((view) => view.id === activeView) ?? views[0];

  return (
    <section className="todo-page">
      <header className="todo-header">
        <div>
          <h1>Todo</h1>
          <p>Remember the next action. Re-plan the work, not the evidence.</p>
        </div>
        <form
          className="quick-capture"
          onSubmit={(event) => {
            event.preventDefault();
            void capture();
          }}
        >
          <input
            aria-label="Quick capture task title"
            placeholder="Quick capture a task…"
            value={captureTitle}
            onChange={(event) => setCaptureTitle(event.target.value)}
            disabled={mutating}
          />
          <select
            aria-label="Quick capture project"
            value={captureProjectId}
            onChange={(event) => setCaptureProjectId(event.target.value)}
            disabled={mutating}
          >
            <option value="">Inbox</option>
            {projects.filter((project) => project.status === "active").map((project) => (
              <option value={project.id} key={project.id}>{project.name}</option>
            ))}
          </select>
          <button type="submit" disabled={mutating || !captureTitle.trim()}>
            <Plus size={15} /> Add
          </button>
        </form>
      </header>

      <nav className="todo-tabs" aria-label="Todo views">
        {views.map((view) => {
          const Icon = view.icon;
          return (
            <button
              className={activeView === view.id ? "active" : ""}
              type="button"
              onClick={() => setActiveView(view.id)}
              key={view.id}
            >
              <Icon size={14} /> {view.label}
            </button>
          );
        })}
      </nav>

      <div className="todo-scroll">
        {error ? <TodoState icon={<AlertCircle size={21} />} title="Todo unavailable" message={error} /> : null}
        {loading ? (
          <TodoState icon={<LoaderCircle className="spin" size={21} />} title={`Loading ${currentView.label}`} message="Reading your local Todo workspace." />
        ) : error ? null : activeView === "today" ? (
          <TodayContent
            data={today}
            projects={projects}
            proposal={proposal}
            taskNames={taskNames}
            mutating={mutating}
            onPatch={patchTask}
            onDelete={deleteTask}
            onGenerate={() => void mutate(async () => {
              const generated = await postTodoJson<PlanProposal>("/api/todo/plan-proposals");
              setProposal(generated);
            })}
            onDecide={(decision) => {
              if (!proposal) return;
              void mutate(async () => {
                const decided = await postTodoJson<PlanProposal>(
                  `/api/todo/plan-proposals/${proposal.id}/${decision}`,
                );
                setProposal(decided);
              });
            }}
          />
        ) : activeView === "projects" ? (
          <ProjectsContent
            projects={projects}
            detail={projectDetail}
            selectedProjectId={selectedProjectId}
            newProjectName={newProjectName}
            projectTaskTitle={projectTaskTitle}
            mutating={mutating}
            onSelect={setSelectedProjectId}
            onNewProjectName={setNewProjectName}
            onProjectTaskTitle={setProjectTaskTitle}
            onCreateProject={() => void mutate(async () => {
              const created = await postTodoJson<Project>("/api/todo/projects", { name: newProjectName });
              setNewProjectName("");
              setSelectedProjectId(created.id);
            })}
            onProjectStatus={(projectId, status) => void mutate(() =>
              patchTodoJson<Project>(`/api/todo/projects/${projectId}`, { status }))}
            onRenameProject={(project) => {
              const name = window.prompt("Project name", project.name)?.trim();
              if (name && name !== project.name) {
                void mutate(() => patchTodoJson<Project>(`/api/todo/projects/${project.id}`, { name }));
              }
            }}
            onDeleteProject={(project) => {
              if (window.confirm(`Delete “${project.name}”? Its tasks will move to Inbox.`)) {
                void mutate(async () => {
                  await deleteTodo(`/api/todo/projects/${project.id}`);
                  setSelectedProjectId("");
                });
              }
            }}
            onAddProjectTask={() => void mutate(async () => {
              if (!selectedProjectId || !projectTaskTitle.trim()) return;
              await postTodoJson<TodoTask>("/api/todo/tasks", {
                title: projectTaskTitle,
                project_id: selectedProjectId,
              });
              setProjectTaskTitle("");
            })}
            onPatch={patchTask}
            onDeleteTask={deleteTask}
          />
        ) : (
          <TaskSection
            title={currentView.label}
            message={emptyMessage(activeView)}
            tasks={items}
            projects={projects}
            onPatch={patchTask}
            onDelete={deleteTask}
          />
        )}
      </div>
    </section>
  );
}

function TodayContent({
  data,
  projects,
  proposal,
  taskNames,
  mutating,
  onPatch,
  onDelete,
  onGenerate,
  onDecide,
}: {
  data: TodayView | null;
  projects: Project[];
  proposal: PlanProposal | null;
  taskNames: Record<string, string>;
  mutating: boolean;
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
  onGenerate: () => void;
  onDecide: (decision: "accept" | "reject") => void;
}) {
  if (!data) return <TodoState icon={<CalendarDays size={21} />} title="No Today data" message="Refresh the Todo API and try again." />;
  return (
    <div className="todo-content today-content">
      <section className="todo-panel planner-panel">
        <div className="todo-section-heading">
          <div><span>AI planner</span><h2>Plan My Day</h2></div>
          <button className="todo-primary" type="button" onClick={onGenerate} disabled={mutating}>
            <Sparkles size={14} /> {proposal?.status === "pending" ? "Generate again" : "Generate plan"}
          </button>
        </div>
        {proposal ? (
          <div className={`proposal-card ${proposal.status}`}>
            <div className="proposal-status">{proposal.status}</div>
            <p>{proposal.summary ?? "The planner returned task-level suggestions."}</p>
            <div className="proposal-items">
              {proposal.items.map((item) => (
                <div key={item.id}>
                  <strong>{taskNames[item.task_id] ?? item.task_id}</strong>
                  <span>Plan {item.suggested_planned_date}{item.suggested_priority ? ` · ${item.suggested_priority}` : ""}</span>
                  {item.reason ? <small>{item.reason}</small> : null}
                </div>
              ))}
            </div>
            {proposal.status === "pending" ? (
              <div className="proposal-actions">
                <button className="todo-primary" type="button" onClick={() => onDecide("accept")} disabled={mutating}>Accept</button>
                <button type="button" onClick={() => onDecide("reject")} disabled={mutating}>Reject</button>
              </div>
            ) : null}
          </div>
        ) : <p className="todo-muted">Generate a proposal to review. Tasks stay unchanged until you accept it.</p>}
      </section>

      <TaskSection title="Carryover" message="Nothing unfinished from previous planned days." tasks={data.carryover} projects={projects} onPatch={onPatch} onDelete={onDelete} />
      <TaskSection title="Planned Today" message="No tasks are planned for today yet." tasks={data.planned_today} projects={projects} onPatch={onPatch} onDelete={onDelete} />

      <section className="todo-panel project-overview-panel">
        <div className="todo-section-heading"><div><span>Across projects</span><h2>Active Projects Overview</h2></div></div>
        {data.active_projects.length ? (
          <div className="project-overview-grid">
            {data.active_projects.map((overview) => (
              <article key={overview.project.id}>
                <div><strong>{overview.project.name}</strong><span>{overview.unfinished_task_count} remaining</span></div>
                <p>{overview.next_action ? <>Next: {overview.next_action.title}</> : "Next action not set"}</p>
              </article>
            ))}
          </div>
        ) : <p className="todo-muted">Create an active Project to make cross-project next actions visible.</p>}
      </section>
    </div>
  );
}

function ProjectsContent({
  projects,
  detail,
  selectedProjectId,
  newProjectName,
  projectTaskTitle,
  mutating,
  onSelect,
  onNewProjectName,
  onProjectTaskTitle,
  onCreateProject,
  onProjectStatus,
  onRenameProject,
  onDeleteProject,
  onAddProjectTask,
  onPatch,
  onDeleteTask,
}: {
  projects: Project[];
  detail: ProjectDetail | null;
  selectedProjectId: string;
  newProjectName: string;
  projectTaskTitle: string;
  mutating: boolean;
  onSelect: (projectId: string) => void;
  onNewProjectName: (name: string) => void;
  onProjectTaskTitle: (title: string) => void;
  onCreateProject: () => void;
  onProjectStatus: (projectId: string, status: ProjectStatus) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  onAddProjectTask: () => void;
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
}) {
  return (
    <div className="projects-workspace">
      <aside className="project-list-panel">
        <form onSubmit={(event) => { event.preventDefault(); onCreateProject(); }}>
          <input placeholder="New project" value={newProjectName} onChange={(event) => onNewProjectName(event.target.value)} />
          <button type="submit" disabled={mutating || !newProjectName.trim()}><Plus size={14} /></button>
        </form>
        <div className="project-list">
          {projects.map((project) => (
            <button className={selectedProjectId === project.id ? "active" : ""} type="button" onClick={() => onSelect(project.id)} key={project.id}>
              <strong>{project.name}</strong><span>{project.status}</span>
            </button>
          ))}
        </div>
      </aside>
      <div className="project-detail-panel">
        {!detail ? (
          <TodoState icon={<ListTodo size={21} />} title="No project selected" message="Create or select a Project to define its next action." />
        ) : (
          <>
            <header className="project-detail-header">
              <div><span>Project</span><h2>{detail.project.name}</h2><p>{detail.next_action ? `Next: ${detail.next_action.title}` : "Next action not set"}</p></div>
              <div>
                <select value={detail.project.status} onChange={(event) => onProjectStatus(detail.project.id, event.target.value as ProjectStatus)} disabled={mutating}>
                  <option value="active">Active</option><option value="paused">Paused</option><option value="archived">Archived</option>
                </select>
                <button type="button" onClick={() => onRenameProject(detail.project)} disabled={mutating}>Rename</button>
                <button className="danger" type="button" onClick={() => onDeleteProject(detail.project)} disabled={mutating}>Delete project</button>
              </div>
            </header>
            <form className="project-add-task" onSubmit={(event) => { event.preventDefault(); onAddProjectTask(); }}>
              <input placeholder="Add a task to this project" value={projectTaskTitle} onChange={(event) => onProjectTaskTitle(event.target.value)} />
              <button className="todo-primary" type="submit" disabled={mutating || !projectTaskTitle.trim()}><Plus size={14} /> Add task</button>
            </form>
            <TaskSection title="Unfinished" message="No unfinished tasks in this Project." tasks={detail.unfinished_tasks} projects={projects} onPatch={onPatch} onDelete={onDeleteTask} />
            <TaskSection title="Completed" message="No completed tasks in this Project." tasks={detail.completed_tasks} projects={projects} onPatch={onPatch} onDelete={onDeleteTask} />
          </>
        )}
      </div>
    </div>
  );
}

function TaskSection({ title, message, tasks, projects, onPatch, onDelete }: {
  title: string;
  message: string;
  tasks: TodoTask[];
  projects: Project[];
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
}) {
  return (
    <section className="todo-panel task-section">
      <div className="todo-section-heading"><div><span>Tasks</span><h2>{title}</h2></div><strong>{tasks.length}</strong></div>
      {tasks.length ? <div className="todo-task-list">{tasks.map((task) => <TaskCard task={task} projects={projects} onPatch={onPatch} onDelete={onDelete} key={task.id} />)}</div> : <p className="todo-muted">{message}</p>}
    </section>
  );
}

function TodoState({ icon, title, message }: { icon: React.ReactNode; title: string; message: string }) {
  return <div className="todo-state"><span>{icon}</span><h2>{title}</h2><p>{message}</p></div>;
}

function messageForError(error: unknown): string {
  if (error instanceof TodoApiError) {
    if (error.code === "todo_planner_unavailable") return "Configure DEEPSEEK_API_KEY before using Plan My Day.";
    return error.message;
  }
  return "The Todo API could not be reached. Restart the changed services and try again.";
}

function emptyMessage(view: TodoView): string {
  if (view === "inbox") return "Quick Capture without a Project to add something to Inbox.";
  if (view === "upcoming") return "No unfinished tasks have a future planned or due date.";
  return "No completed tasks yet.";
}
