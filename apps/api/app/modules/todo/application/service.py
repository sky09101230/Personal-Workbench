from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.modules.todo.application.errors import (
    TodoNotFoundError,
    TodoPlannerUnavailableError,
    TodoValidationError,
)
from app.modules.todo.application.ports import TodoPlannerPort, TodoRepository
from app.modules.todo.domain.models import (
    PlanProposal,
    PlanProposalItem,
    PlannerContext,
    Project,
    ProjectDetail,
    ProjectStatus,
    ProposalStatus,
    Task,
    TaskPriority,
    TaskStatus,
    TodayView,
    UNFINISHED_TASK_STATUSES,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")


class TodoService:
    def __init__(
        self,
        repository: TodoRepository,
        planner: TodoPlannerPort | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.clock = clock

    def create_project(
        self,
        *,
        name: str,
        status: ProjectStatus = ProjectStatus.ACTIVE,
        order: int = 0,
    ) -> Project:
        now = self._now()
        project = Project(
            id=str(uuid4()),
            name=_required_text(name, "Project name"),
            status=status,
            order=order,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create_project(project)

    def get_project(self, project_id: str) -> Project:
        project = self.repository.get_project(project_id)
        if project is None:
            raise TodoNotFoundError("Project was not found")
        return project

    def list_projects(self, *, status: ProjectStatus | None = None) -> tuple[Project, ...]:
        return self.repository.list_projects(status=status)

    def update_project(self, project_id: str, changes: Mapping[str, object]) -> Project:
        project = self.get_project(project_id)
        allowed = {"name", "status", "order"}
        _reject_unknown(changes, allowed)
        updated = replace(
            project,
            name=(
                _required_text(changes["name"], "Project name")
                if "name" in changes
                else project.name
            ),
            status=(
                _enum_value(ProjectStatus, changes["status"], "Project status")
                if "status" in changes
                else project.status
            ),
            order=(
                _required_integer(changes["order"], "Project order")
                if "order" in changes
                else project.order
            ),
            updated_at=self._now(),
        )
        return self.repository.update_project(updated)

    def delete_project(self, project_id: str) -> None:
        self.get_project(project_id)
        if not self.repository.delete_project(project_id):
            raise TodoNotFoundError("Project was not found")

    def project_detail(self, project_id: str) -> ProjectDetail:
        project = self.get_project(project_id)
        tasks = self.repository.list_tasks_for_project(project_id)
        unfinished = tuple(task for task in tasks if task.status in UNFINISHED_TASK_STATUSES)
        completed = tuple(task for task in tasks if task.status is TaskStatus.DONE)
        next_action = next((task for task in unfinished if task.is_next_action), None)
        return ProjectDetail(
            project=project,
            next_action=next_action,
            unfinished_tasks=unfinished,
            completed_tasks=completed,
        )

    def create_task(
        self,
        *,
        title: str,
        project_id: str | None = None,
        description: str | None = None,
        status: TaskStatus = TaskStatus.TODO,
        priority: TaskPriority | None = None,
        due_date: date | None = None,
        planned_date: date | None = None,
        is_next_action: bool = False,
    ) -> Task:
        if project_id is not None:
            project = self.get_project(project_id)
        else:
            project = None
        if is_next_action:
            self._validate_next_action(project, status)
        now = self._now()
        task = Task(
            id=str(uuid4()),
            project_id=project_id,
            title=_required_text(title, "Task title"),
            description=_optional_text(description),
            status=status,
            priority=priority,
            due_date=due_date,
            planned_date=planned_date,
            is_next_action=is_next_action,
            created_at=now,
            updated_at=now,
            completed_at=now if status is TaskStatus.DONE else None,
        )
        return self.repository.create_task(task)

    def get_task(self, task_id: str) -> Task:
        task = self.repository.get_task(task_id)
        if task is None:
            raise TodoNotFoundError("Task was not found")
        return task

    def list_tasks(self) -> tuple[Task, ...]:
        return self.repository.list_tasks()

    def update_task(self, task_id: str, changes: Mapping[str, object]) -> Task:
        task = self.get_task(task_id)
        allowed = {
            "project_id",
            "title",
            "description",
            "status",
            "priority",
            "due_date",
            "planned_date",
            "is_next_action",
        }
        _reject_unknown(changes, allowed)
        project_id = changes.get("project_id", task.project_id)
        project_id = str(project_id) if project_id is not None else None
        project = self.get_project(project_id) if project_id is not None else None
        status = (
            _enum_value(TaskStatus, changes["status"], "Task status")
            if "status" in changes
            else task.status
        )
        explicitly_set_next_action = changes.get("is_next_action") is True
        next_action = bool(changes.get("is_next_action", task.is_next_action))
        if explicitly_set_next_action:
            self._validate_next_action(project, status)
        if project_id is None or status not in UNFINISHED_TASK_STATUSES:
            next_action = False
        elif project is not None and project.status is not ProjectStatus.ACTIVE:
            next_action = False
        now = self._now()
        completed_at = task.completed_at
        if status is TaskStatus.DONE and task.status is not TaskStatus.DONE:
            completed_at = now
        elif status is not TaskStatus.DONE:
            completed_at = None
        priority = task.priority
        if "priority" in changes:
            priority = (
                None
                if changes["priority"] is None
                else _enum_value(TaskPriority, changes["priority"], "Task priority")
            )
        updated = replace(
            task,
            project_id=project_id,
            title=(
                _required_text(changes["title"], "Task title")
                if "title" in changes
                else task.title
            ),
            description=(
                _optional_text(changes["description"])
                if "description" in changes
                else task.description
            ),
            status=status,
            priority=priority,
            due_date=changes.get("due_date", task.due_date),
            planned_date=changes.get("planned_date", task.planned_date),
            is_next_action=next_action,
            updated_at=now,
            completed_at=completed_at,
        )
        return self.repository.update_task(updated)

    def delete_task(self, task_id: str) -> None:
        self.get_task(task_id)
        if not self.repository.delete_task(task_id):
            raise TodoNotFoundError("Task was not found")

    def inbox(self) -> tuple[Task, ...]:
        return self.repository.list_inbox()

    def today(self) -> TodayView:
        today = self._local_now().date()
        carryover, planned_today = self.repository.list_today_tasks(today)
        return TodayView(
            date=today,
            carryover=carryover,
            planned_today=planned_today,
            active_projects=self.repository.list_project_overviews(),
        )

    def upcoming(self) -> tuple[Task, ...]:
        return self.repository.list_upcoming(self._local_now().date())

    def completed(self) -> tuple[Task, ...]:
        return self.repository.list_completed()

    def generate_plan(self) -> PlanProposal:
        if self.planner is None:
            raise TodoPlannerUnavailableError("Todo planner is not available")
        local_now = self._local_now()
        active_projects = self.repository.list_projects(status=ProjectStatus.ACTIVE)
        active_project_ids = {project.id for project in active_projects}
        unfinished = tuple(
            task
            for task in self.repository.list_unfinished()
            if task.project_id is None or task.project_id in active_project_ids
        )
        carryover, planned_today = self.repository.list_today_tasks(local_now.date())
        eligible_ids = {task.id for task in unfinished}
        carryover = tuple(task for task in carryover if task.id in eligible_ids)
        planned_today = tuple(task for task in planned_today if task.id in eligible_ids)
        context = PlannerContext(
            current_datetime=local_now,
            current_date=local_now.date(),
            active_projects=active_projects,
            unfinished_tasks=unfinished,
            carryover_tasks=carryover,
            planned_today_tasks=planned_today,
            next_actions=tuple(task for task in unfinished if task.is_next_action),
        )
        result = self.planner.plan_day(context)
        seen: set[str] = set()
        proposal_id = str(uuid4())
        items: list[PlanProposalItem] = []
        for suggestion in result.items:
            if suggestion.task_id not in eligible_ids:
                raise TodoValidationError("Planner referenced an ineligible Task")
            if suggestion.task_id in seen:
                raise TodoValidationError("Planner returned a duplicate Task")
            if suggestion.suggested_planned_date < local_now.date():
                raise TodoValidationError("Planner returned a past planned date")
            seen.add(suggestion.task_id)
            items.append(
                PlanProposalItem(
                    id=str(uuid4()),
                    proposal_id=proposal_id,
                    task_id=suggestion.task_id,
                    suggested_planned_date=suggestion.suggested_planned_date,
                    suggested_priority=suggestion.suggested_priority,
                    reason=_optional_text(suggestion.reason),
                )
            )
        proposal = PlanProposal(
            id=proposal_id,
            status=ProposalStatus.PENDING,
            summary=_optional_text(result.summary),
            created_at=self._now(),
            decided_at=None,
            items=tuple(items),
        )
        return self.repository.create_proposal(proposal)

    def get_proposal(self, proposal_id: str) -> PlanProposal:
        proposal = self.repository.get_proposal(proposal_id)
        if proposal is None:
            raise TodoNotFoundError("Plan proposal was not found")
        return proposal

    def accept_proposal(self, proposal_id: str) -> PlanProposal:
        self.get_proposal(proposal_id)
        return self.repository.accept_proposal(proposal_id, decided_at=self._now())

    def reject_proposal(self, proposal_id: str) -> PlanProposal:
        self.get_proposal(proposal_id)
        return self.repository.reject_proposal(proposal_id, decided_at=self._now())

    def _validate_next_action(
        self,
        project: Project | None,
        status: TaskStatus,
    ) -> None:
        if project is None:
            raise TodoValidationError("An Inbox Task cannot be a Next Action")
        if project.status is not ProjectStatus.ACTIVE:
            raise TodoValidationError("Only an active Project can have a Next Action")
        if status not in UNFINISHED_TASK_STATUSES:
            raise TodoValidationError("A finished Task cannot be a Next Action")

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Todo clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    def _local_now(self) -> datetime:
        return self._now().astimezone(_SHANGHAI)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TodoValidationError(f"{label} is required")
    text = value.strip()
    if not text:
        raise TodoValidationError(f"{label} is required")
    return text


def _required_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TodoValidationError(f"{label} is invalid")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reject_unknown(changes: Mapping[str, object], allowed: set[str]) -> None:
    unknown = set(changes) - allowed
    if unknown:
        raise TodoValidationError(f"Unsupported fields: {', '.join(sorted(unknown))}")


def _enum_value(enum_type, value: object, label: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise TodoValidationError(f"{label} is invalid") from error
