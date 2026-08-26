from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


UNFINISHED_TASK_STATUSES = (TaskStatus.TODO, TaskStatus.DOING)


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    status: ProjectStatus
    order: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Task:
    id: str
    project_id: str | None
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority | None
    due_date: date | None
    planned_date: date | None
    is_next_action: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class ProjectOverview:
    project: Project
    unfinished_task_count: int
    next_action: Task | None


@dataclass(frozen=True)
class ProjectDetail:
    project: Project
    next_action: Task | None
    unfinished_tasks: tuple[Task, ...]
    completed_tasks: tuple[Task, ...]


@dataclass(frozen=True)
class TodayView:
    date: date
    carryover: tuple[Task, ...]
    planned_today: tuple[Task, ...]
    active_projects: tuple[ProjectOverview, ...]


@dataclass(frozen=True)
class PlannerContext:
    current_datetime: datetime
    current_date: date
    active_projects: tuple[Project, ...]
    unfinished_tasks: tuple[Task, ...]
    carryover_tasks: tuple[Task, ...]
    planned_today_tasks: tuple[Task, ...]
    next_actions: tuple[Task, ...]


@dataclass(frozen=True)
class PlannerSuggestion:
    task_id: str
    suggested_planned_date: date
    suggested_priority: TaskPriority | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PlannerResult:
    summary: str | None
    items: tuple[PlannerSuggestion, ...]


@dataclass(frozen=True)
class PlanProposalItem:
    id: str
    proposal_id: str
    task_id: str
    suggested_planned_date: date
    suggested_priority: TaskPriority | None
    reason: str | None


@dataclass(frozen=True)
class PlanProposal:
    id: str
    status: ProposalStatus
    summary: str | None
    created_at: datetime
    decided_at: datetime | None
    items: tuple[PlanProposalItem, ...]
