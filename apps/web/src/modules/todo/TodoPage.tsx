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
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

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
  // Server-canonical completed items, read when composing an array patch.
  const completedItemsRef = useRef<string[]>([]);
  // Description draft survives reconciliation; it may only be overwritten
  // while the field is not focused (design decision 4).
  const [projectDescDraft, setProjectDescDraft] = useState("");
  const descFocusedRef = useRef(false);

  const [proposal, setProposal] = useState<PlanProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [capturePending, setCapturePending] = useState(false);
  const [createProjectPending, setCreateProjectPending] = useState(false);
  const [plannerBusy, setPlannerBusy] = useState(false);
  const [bulkMoveBusy, setBulkMoveBusy] = useState(false);

  const loadBase = useCallback(async () => {
    const [projectResult, taskResult] = await Promise.all([
      getTodoJson<ItemList<Project>>("/api/todo/projects"),
      getTodoJson<ItemList<TodoTask>>("/api/todo/tasks"),
    ]);
    setProjects(projectResult.items);
    setAllTasks(taskResult.items);
    setSelectedProjectId(
      (current) =>
        current ||
        projectResult.items.find((project) => project.status === "active")?.id ||
        "",
    );
  }, []);

  const loadView = useCallback(async () => {
    if (activeView === "today") {
      setToday(await getTodoJson<TodayView>("/api/todo/today"));
      return;
    }
    if (activeView === "projects") {
      if (selectedProjectId) {
        const loaded = await getTodoJson<ProjectDetail>(
          `/api/todo/projects/${selectedProjectId}/detail`,
        );
        setProjectDetail(loaded);
        completedItemsRef.current = [...loaded.project.completed_items];
        if (!descFocusedRef.current) {
          setProjectDescDraft(loaded.project.description ?? "");
        }
      } else {
        setProjectDetail(null);
      }
      return;
    }
    const endpoint = activeView === "inbox" ? "inbox" : activeView;
    setItems((await getTodoJson<ItemList<TodoTask>>(`/api/todo/${endpoint}`)).items);
  }, [activeView, selectedProjectId]);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    void Promise.all([loadBase(), loadView()])
      .catch((requestError) => setLoadError(messageForError(requestError)))
      .finally(() => setLoading(false));
  }, [loadBase, loadView]);

  // Silent background reconciliation: single-flight, rerun if requested while
  // another round was still running so responses never interleave stale writes.
  const reconcilingRef = useRef(false);
  const reconcileRerunRef = useRef(false);
  const reconcile = useCallback(async () => {
    if (reconcilingRef.current) {
      reconcileRerunRef.current = true;
      return;
    }
    reconcilingRef.current = true;
    try {
      do {
        reconcileRerunRef.current = false;
        await Promise.all([loadBase(), loadView()]);
      } while (reconcileRerunRef.current);
    } catch (backgroundError) {
      console.warn("Todo reconciliation failed", backgroundError);
    } finally {
      reconcilingRef.current = false;
    }
  }, [loadBase, loadView]);

  useEffect(() => {
    completedItemsRef.current = projectDetail ? [...projectDetail.project.completed_items] : [];
  }, [projectDetail]);

  const updateTaskLocally = useCallback(
    (taskId: string, updater: (task: TodoTask) => TodoTask) => {
      const swap = (list: TodoTask[]) => list.map((task) => (task.id === taskId ? updater(task) : task));
      setAllTasks(swap);
      setItems(swap);
      setToday((current) =>
        current && {
          ...current,
          carryover: swap(current.carryover),
          planned_today: swap(current.planned_today),
          active_projects: current.active_projects.map((overview) =>
            overview.next_action?.id === taskId
              ? { ...overview, next_action: updater(overview.next_action) }
              : overview,
          ),
        },
      );
      setProjectDetail((current) =>
        current && {
          ...current,
          next_action: current.next_action?.id === taskId ? updater(current.next_action) : current.next_action,
          unfinished_tasks: swap(current.unfinished_tasks),
          completed_tasks: swap(current.completed_tasks),
        },
      );
    },
    [],
  );

  const removeTaskLocally = useCallback((taskId: string) => {
    const drop = (list: TodoTask[]) => list.filter((task) => task.id !== taskId);
    setAllTasks(drop);
    setItems(drop);
    setToday(
      (current) =>
        current && {
          ...current,
          carryover: drop(current.carryover),
          planned_today: drop(current.planned_today),
          active_projects: current.active_projects.map((overview) =>
            overview.next_action?.id === taskId ? { ...overview, next_action: null } : overview,
          ),
        },
    );
    setProjectDetail(
      (current) =>
        current && {
          ...current,
          next_action: current.next_action?.id === taskId ? null : current.next_action,
          unfinished_tasks: drop(current.unfinished_tasks),
          completed_tasks: drop(current.completed_tasks),
        },
    );
  }, []);

  const updateProjectLocally = useCallback(
    (projectId: string, updater: (project: Project) => Project) => {
      const swap = (list: Project[]) => list.map((project) => (project.id === projectId ? updater(project) : project));
      setProjects(swap);
      setToday(
        (current) =>
          current && {
            ...current,
            active_projects: current.active_projects.map((overview) =>
              overview.project.id === projectId ? { ...overview, project: updater(overview.project) } : overview,
            ),
          },
      );
      setProjectDetail((current) =>
        current && current.project.id === projectId ? { ...current, project: updater(current.project) } : current,
      );
    },
    [],
  );

  const removeProjectLocally = useCallback((projectId: string) => {
    setProjects((prev) => prev.filter((project) => project.id !== projectId));
    setToday(
      (current) =>
        current && {
          ...current,
          active_projects: current.active_projects.filter((overview) => overview.project.id !== projectId),
        },
    );
    setProjectDetail((current) => (current && current.project.id === projectId ? null : current));
    setSelectedProjectId((current) => (current === projectId ? "" : current));
  }, []);

  // Serialize project writes whose payload depends on current server state
  // (completed_items array replacement), preventing rapid edits from dropping
  // each other's changes.
  const projectWriteChainRef = useRef<Promise<unknown>>(Promise.resolve());
  const enqueueProjectWrite = useCallback(<T,>(job: () => Promise<T>): Promise<T> => {
    const result = projectWriteChainRef.current.then(job, job);
    projectWriteChainRef.current = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }, []);

  const writeWithRollback = useCallback(
    async (
      perform: () => Promise<unknown>,
      optimistic?: () => void,
    ) => {
      setActionError(null);
      optimistic?.();
      try {
        await perform();
      } catch (requestError) {
        setActionError(messageForError(requestError));
      } finally {
        void reconcile();
      }
    },
    [reconcile],
  );

  const patchTask = useCallback(
    (taskId: string, patch: TaskPatch) =>
      writeWithRollback(
        () => patchTodoJson<TodoTask>(`/api/todo/tasks/${taskId}`, patch),
        () => updateTaskLocally(taskId, (task) => ({ ...task, ...patch })),
      ),
    [writeWithRollback, updateTaskLocally],
  );

  const deleteTask = useCallback(
    (taskId: string) =>
      writeWithRollback(
        () => deleteTodo(`/api/todo/tasks/${taskId}`),
        () => removeTaskLocally(taskId),
      ),
    [writeWithRollback, removeTaskLocally],
  );

  const rescheduleToToday = useCallback(
    (taskId: string) => {
      const date = todayIso();
      return writeWithRollback(
        () => patchTodoJson<TodoTask>(`/api/todo/tasks/${taskId}`, { planned_date: date }),
        () => updateTaskLocally(taskId, (task) => ({ ...task, planned_date: date })),
      );
    },
    [writeWithRollback, updateTaskLocally],
  );

  const moveAllCarryoverToToday = useCallback(async () => {
    if (!today || !today.carryover.length) return;
    const date = todayIso();
    setActionError(null);
    setBulkMoveBusy(true);
    let failures = 0;
    try {
      for (const task of today.carryover) {
        updateTaskLocally(task.id, (item) => ({ ...item, planned_date: date }));
        try {
          await patchTodoJson<TodoTask>(`/api/todo/tasks/${task.id}`, { planned_date: date });
        } catch {
          failures += 1;
          updateTaskLocally(task.id, (item) => ({ ...item, planned_date: task.planned_date }));
        }
      }
    } finally {
      setBulkMoveBusy(false);
    }
    if (failures > 0) {
      setActionError(`${failures} 个任务移动失败，已保留原计划日期。`);
    }
    void reconcile();
  }, [today, updateTaskLocally, reconcile]);

  const patchProject = useCallback(
    (projectId: string, patch: Partial<Pick<Project, "name" | "status">>) =>
      writeWithRollback(
        () => enqueueProjectWrite(() => patchTodoJson<Project>(`/api/todo/projects/${projectId}`, patch)),
        () => updateProjectLocally(projectId, (project) => ({ ...project, ...patch })),
      ),
    [writeWithRollback, enqueueProjectWrite, updateProjectLocally],
  );

  const saveProjectDescription = useCallback(
    (projectId: string) => {
      const description = projectDescDraft.trim() || null;
      return writeWithRollback(
        () =>
          enqueueProjectWrite(async () => {
            const saved = await patchTodoJson<Project>(`/api/todo/projects/${projectId}`, { description });
            if (!descFocusedRef.current) {
              setProjectDescDraft(saved.description ?? "");
            }
            return saved;
          }),
        () => updateProjectLocally(projectId, (project) => ({ ...project, description })),
      );
    },
    [writeWithRollback, enqueueProjectWrite, updateProjectLocally, projectDescDraft],
  );

  const addCompletedItem = useCallback(
    (projectId: string, item: string): Promise<void> => {
      const persist = async () => {
        const saved = await enqueueProjectWrite(async () => {
          const payload = [...completedItemsRef.current, item];
          const savedProject = await patchTodoJson<Project>(`/api/todo/projects/${projectId}`, {
            completed_items: payload,
          });
          completedItemsRef.current = [...savedProject.completed_items];
          return savedProject;
        });
        return saved;
      };
      return writeWithRollback(
        persist,
        () =>
          updateProjectLocally(projectId, (project) => ({
            ...project,
            completed_items: [...project.completed_items, item],
          })),
      ).then(() => undefined);
    },
    [writeWithRollback, enqueueProjectWrite, updateProjectLocally],
  );

  const removeCompletedItem = useCallback(
    (projectId: string, index: number): Promise<void> => {
      const persist = () =>
        enqueueProjectWrite(async () => {
          const payload = completedItemsRef.current.filter((_, position) => position !== index);
          const savedProject = await patchTodoJson<Project>(`/api/todo/projects/${projectId}`, {
            completed_items: payload,
          });
          completedItemsRef.current = [...savedProject.completed_items];
          return savedProject;
        });
      return writeWithRollback(
        persist,
        () =>
          updateProjectLocally(projectId, (project) => ({
            ...project,
            completed_items: project.completed_items.filter((_, position) => position !== index),
          })),
      ).then(() => undefined);
    },
    [writeWithRollback, enqueueProjectWrite, updateProjectLocally],
  );

  const deleteProject = useCallback(
    (projectId: string) =>
      writeWithRollback(
        () => deleteTodo(`/api/todo/projects/${projectId}`),
        () => removeProjectLocally(projectId),
      ),
    [writeWithRollback, removeProjectLocally],
  );

  const capture = async () => {
    const title = captureTitle.trim();
    if (!title || capturePending) return;
    setCapturePending(true);
    setActionError(null);
    try {
      await postTodoJson<TodoTask>("/api/todo/tasks", {
        title,
        project_id: captureProjectId || null,
      });
      setCaptureTitle("");
    } catch (requestError) {
      setActionError(messageForError(requestError));
    } finally {
      setCapturePending(false);
      void reconcile();
    }
  };

  const createProject = async () => {
    const name = newProjectName.trim();
    if (!name || createProjectPending) return;
    setCreateProjectPending(true);
    setActionError(null);
    try {
      const created = await postTodoJson<Project>("/api/todo/projects", { name });
      setNewProjectName("");
      setSelectedProjectId(created.id);
    } catch (requestError) {
      setActionError(messageForError(requestError));
    } finally {
      setCreateProjectPending(false);
      void reconcile();
    }
  };

  const addProjectTask = async () => {
    const title = projectTaskTitle.trim();
    if (!selectedProjectId || !title) return;
    await writeWithRollback(async () => {
      await postTodoJson<TodoTask>("/api/todo/tasks", {
        title,
        project_id: selectedProjectId,
      });
      setProjectTaskTitle("");
    });
  };

  const generatePlan = async () => {
    if (plannerBusy) return;
    setPlannerBusy(true);
    setActionError(null);
    try {
      setProposal(await postTodoJson<PlanProposal>("/api/todo/plan-proposals"));
    } catch (requestError) {
      setActionError(messageForError(requestError));
    } finally {
      setPlannerBusy(false);
    }
  };

  const decidePlan = useCallback(
    async (decision: "accept" | "reject") => {
      if (!proposal || plannerBusy) return;
      setPlannerBusy(true);
      setActionError(null);
      try {
        setProposal(
          await postTodoJson<PlanProposal>(`/api/todo/plan-proposals/${proposal.id}/${decision}`),
        );
      } catch (requestError) {
        setActionError(messageForError(requestError));
      } finally {
        setPlannerBusy(false);
        void reconcile();
      }
    },
    [proposal, plannerBusy, reconcile],
  );

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
          />
          <select
            aria-label="Quick capture project"
            value={captureProjectId}
            onChange={(event) => setCaptureProjectId(event.target.value)}
          >
            <option value="">Inbox</option>
            {projects.filter((project) => project.status === "active").map((project) => (
              <option value={project.id} key={project.id}>{project.name}</option>
            ))}
          </select>
          <button type="submit" disabled={capturePending || !captureTitle.trim()}>
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
        {loadError ? <TodoState icon={<AlertCircle size={21} />} title="Todo unavailable" message={loadError} /> : null}
        {actionError ? (
          <div className="todo-action-error" role="alert">
            <span>
              <AlertCircle size={13} /> {actionError}
            </span>
            <button type="button" onClick={() => setActionError(null)} aria-label="Dismiss error">
              <X size={13} />
            </button>
          </div>
        ) : null}
        {loading ? (
          <TodoState
            icon={<LoaderCircle className="spin" size={21} />}
            title={`Loading ${currentView.label}`}
            message="Reading your local Todo workspace."
          />
        ) : !loadError && activeView === "today" ? (
          <TodayContent
            data={today}
            projects={projects}
            proposal={proposal}
            taskNames={taskNames}
            plannerBusy={plannerBusy}
            bulkMoveBusy={bulkMoveBusy}
            onGenerate={() => void generatePlan()}
            onDecide={(decision) => void decidePlan(decision)}
            onPatch={patchTask}
            onDelete={deleteTask}
            onRescheduleToday={rescheduleToToday}
            onBulkMoveToday={() => void moveAllCarryoverToToday()}
          />
        ) : !loadError && activeView === "projects" ? (
          <ProjectsContent
            projects={projects}
            detail={projectDetail}
            selectedProjectId={selectedProjectId}
            newProjectName={newProjectName}
            projectTaskTitle={projectTaskTitle}
            onSelect={(projectId) => {
              descFocusedRef.current = false;
              setSelectedProjectId(projectId);
            }}
            onNewProjectName={setNewProjectName}
            onCreateProject={() => void createProject()}
            createProjectPending={createProjectPending}
            onProjectTaskTitle={setProjectTaskTitle}
            onAddProjectTask={() => void addProjectTask()}
            projectDescDraft={projectDescDraft}
            onProjectDescChange={setProjectDescDraft}
            onProjectDescFocus={() => {
              descFocusedRef.current = true;
            }}
            onProjectDescBlur={() => {
              descFocusedRef.current = false;
              if (selectedProjectId) void saveProjectDescription(selectedProjectId);
            }}
            onCompletedItemAdd={(item) =>
              selectedProjectId ? void addCompletedItem(selectedProjectId, item) : Promise.resolve()
            }
            onCompletedItemRemove={(index) =>
              selectedProjectId ? void removeCompletedItem(selectedProjectId, index) : Promise.resolve()
            }
            onPatch={patchTask}
            onDeleteTask={deleteTask}
            onProjectStatus={(projectId, projectStatus) => void patchProject(projectId, { status: projectStatus })}
            onRenameProject={(project) => {
              const name = window.prompt("Project name", project.name)?.trim();
              if (name && name !== project.name) void patchProject(project.id, { name });
            }}
            onDeleteProject={(project) => {
              if (window.confirm(`Delete “${project.name}”? Its tasks will move to Inbox.`)) {
                void deleteProject(project.id);
              }
            }}
          />
        ) : !loadError ? (
          <TaskSection
            title={currentView.label}
            message={emptyMessage(activeView)}
            tasks={items}
            projects={projects}
            onPatch={patchTask}
            onDelete={deleteTask}
            onRescheduleToday={activeView === "upcoming" ? rescheduleToToday : undefined}
          />
        ) : null}
      </div>
    </section>
  );
}

function TodayContent({
  data,
  projects,
  proposal,
  taskNames,
  plannerBusy,
  bulkMoveBusy,
  onGenerate,
  onDecide,
  onPatch,
  onDelete,
  onRescheduleToday,
  onBulkMoveToday,
}: {
  data: TodayView | null;
  projects: Project[];
  proposal: PlanProposal | null;
  taskNames: Record<string, string>;
  plannerBusy: boolean;
  bulkMoveBusy: boolean;
  onGenerate: () => void;
  onDecide: (decision: "accept" | "reject") => void;
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
  onRescheduleToday: (taskId: string) => Promise<void>;
  onBulkMoveToday: () => void;
}) {
  if (!data) return <TodoState icon={<CalendarDays size={21} />} title="No Today data" message="Refresh the Todo API and try again." />;
  return (
    <div className="todo-content today-content">
      <section className="todo-panel planner-panel">
        <div className="todo-section-heading">
          <div><span>AI planner</span><h2>Plan My Day</h2></div>
          <button className="todo-primary" type="button" onClick={onGenerate} disabled={plannerBusy}>
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
                <button className="todo-primary" type="button" onClick={() => onDecide("accept")} disabled={plannerBusy}>Accept</button>
                <button type="button" onClick={() => onDecide("reject")} disabled={plannerBusy}>Reject</button>
              </div>
            ) : null}
          </div>
        ) : <p className="todo-muted">Generate a proposal to review. Tasks stay unchanged until you accept it.</p>}
      </section>

      <TaskSection
        title="Carryover"
        message="Nothing unfinished from previous planned days."
        tasks={data.carryover}
        projects={projects}
        onPatch={onPatch}
        onDelete={onDelete}
        onRescheduleToday={onRescheduleToday}
        headerAction={
          data.carryover.length > 1 ? (
            <button className="todo-secondary" type="button" onClick={onBulkMoveToday} disabled={bulkMoveBusy}>
              全部移到今天
            </button>
          ) : undefined
        }
      />
      <TaskSection
        title="Planned Today"
        message="No tasks are planned for today yet."
        tasks={data.planned_today}
        projects={projects}
        onPatch={onPatch}
        onDelete={onDelete}
      />

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
  onSelect,
  onNewProjectName,
  onCreateProject,
  createProjectPending,
  onProjectTaskTitle,
  onAddProjectTask,
  projectDescDraft,
  onProjectDescChange,
  onProjectDescFocus,
  onProjectDescBlur,
  onCompletedItemAdd,
  onCompletedItemRemove,
  onPatch,
  onDeleteTask,
  onProjectStatus,
  onRenameProject,
  onDeleteProject,
}: {
  projects: Project[];
  detail: ProjectDetail | null;
  selectedProjectId: string;
  newProjectName: string;
  projectTaskTitle: string;
  onSelect: (projectId: string) => void;
  onNewProjectName: (name: string) => void;
  onCreateProject: () => void;
  createProjectPending: boolean;
  onProjectTaskTitle: (title: string) => void;
  onAddProjectTask: () => void;
  projectDescDraft: string;
  onProjectDescChange: (value: string) => void;
  onProjectDescFocus: () => void;
  onProjectDescBlur: () => void;
  onCompletedItemAdd: (item: string) => void;
  onCompletedItemRemove: (index: number) => void;
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
  onProjectStatus: (projectId: string, status: ProjectStatus) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
}) {
  const [completedDraft, setCompletedDraft] = useState("");

  return (
    <div className="projects-workspace">
      <aside className="project-list-panel">
        <form onSubmit={(event) => { event.preventDefault(); onCreateProject(); }}>
          <input placeholder="New project" value={newProjectName} onChange={(event) => onNewProjectName(event.target.value)} />
          <button type="submit" disabled={createProjectPending || !newProjectName.trim()}><Plus size={14} /></button>
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
                <select value={detail.project.status} onChange={(event) => onProjectStatus(detail.project.id, event.target.value as ProjectStatus)}>
                  <option value="active">Active</option><option value="paused">Paused</option><option value="archived">Archived</option>
                </select>
                <button type="button" onClick={() => onRenameProject(detail.project)}>Rename</button>
                <button className="danger" type="button" onClick={() => onDeleteProject(detail.project)}>Delete project</button>
              </div>
            </header>
            <form className="project-add-task" onSubmit={(event) => { event.preventDefault(); onAddProjectTask(); }}>
              <input placeholder="Add a task to this project" value={projectTaskTitle} onChange={(event) => onProjectTaskTitle(event.target.value)} />
              <button className="todo-primary" type="submit" disabled={!projectTaskTitle.trim()}><Plus size={14} /> Add task</button>
            </form>
            <section className="project-info-editor">
              <label>
                <span>Project description（失焦自动保存）</span>
                <textarea
                  value={projectDescDraft}
                  onChange={(event) => onProjectDescChange(event.target.value)}
                  onFocus={onProjectDescFocus}
                  onBlur={onProjectDescBlur}
                  placeholder="这个项目是做什么的？"
                />
              </label>
              <div className="completed-items-editor">
                <span>已完成事项（逐条即时保存）</span>
                {detail.project.completed_items.map((item, index) => (
                  <div key={`${item}-${index}`}>
                    <span>{item}</span>
                    <button type="button" onClick={() => onCompletedItemRemove(index)}>×</button>
                  </div>
                ))}
                <form onSubmit={(event) => {
                  event.preventDefault();
                  const item = completedDraft.trim();
                  if (!item) return;
                  onCompletedItemAdd(item);
                  setCompletedDraft("");
                }}>
                  <input value={completedDraft} onChange={(event) => setCompletedDraft(event.target.value)} placeholder="手动添加已完成事项" />
                  <button type="submit" disabled={!completedDraft.trim()}><Plus size={13} /> 添加</button>
                </form>
              </div>
            </section>
            <TaskSection title="Unfinished" message="No unfinished tasks in this Project." tasks={detail.unfinished_tasks} projects={projects} onPatch={onPatch} onDelete={onDeleteTask} />
            <TaskSection title="Completed" message="No completed tasks in this Project." tasks={detail.completed_tasks} projects={projects} onPatch={onPatch} onDelete={onDeleteTask} />
            <p className="completed-source-note">已完成事项包含手动记录和上方自动归并的 completed tasks。</p>
          </>
        )}
      </div>
    </div>
  );
}

function TaskSection({ title, message, tasks, projects, onPatch, onDelete, onRescheduleToday, headerAction }: {
  title: string;
  message: string;
  tasks: TodoTask[];
  projects: Project[];
  onPatch: (taskId: string, patch: TaskPatch) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
  onRescheduleToday?: (taskId: string) => Promise<void>;
  headerAction?: React.ReactNode;
}) {
  return (
    <section className="todo-panel task-section">
      <div className="todo-section-heading">
        <div><span>Tasks</span><h2>{title}</h2></div>
        <div className="heading-side">
          {headerAction}
          <strong>{tasks.length}</strong>
        </div>
      </div>
      {tasks.length ? <div className="todo-task-list">{tasks.map((task) => <TaskCard task={task} projects={projects} onPatch={onPatch} onDelete={onDelete} onRescheduleToday={onRescheduleToday} key={task.id} />)}</div> : <p className="todo-muted">{message}</p>}
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
