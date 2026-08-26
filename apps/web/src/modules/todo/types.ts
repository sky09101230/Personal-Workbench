export type ProjectStatus = "active" | "paused" | "archived";
export type TaskStatus = "todo" | "doing" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";
export type ProposalStatus = "pending" | "accepted" | "rejected";

export type Project = {
  id: string;
  name: string;
  status: ProjectStatus;
  order: number;
  created_at: string;
  updated_at: string;
};

export type TodoTask = {
  id: string;
  project_id: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority | null;
  due_date: string | null;
  planned_date: string | null;
  is_next_action: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type ProjectOverview = {
  project: Project;
  unfinished_task_count: number;
  next_action: TodoTask | null;
};

export type TodayView = {
  date: string;
  carryover: TodoTask[];
  planned_today: TodoTask[];
  active_projects: ProjectOverview[];
};

export type ProjectDetail = {
  project: Project;
  next_action: TodoTask | null;
  unfinished_tasks: TodoTask[];
  completed_tasks: TodoTask[];
};

export type PlanProposalItem = {
  id: string;
  proposal_id: string;
  task_id: string;
  suggested_planned_date: string;
  suggested_priority: TaskPriority | null;
  reason: string | null;
};

export type PlanProposal = {
  id: string;
  status: ProposalStatus;
  summary: string | null;
  created_at: string;
  decided_at: string | null;
  items: PlanProposalItem[];
};

export type ItemList<T> = { items: T[] };

export type TaskPatch = Partial<Pick<
  TodoTask,
  | "project_id"
  | "title"
  | "description"
  | "status"
  | "priority"
  | "due_date"
  | "planned_date"
  | "is_next_action"
>>;
