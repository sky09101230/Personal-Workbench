from datetime import date, datetime
from typing import Protocol

from app.modules.todo.domain.models import (
    PlanProposal,
    PlannerContext,
    PlannerResult,
    Project,
    ProjectOverview,
    ProjectStatus,
    Task,
)


class TodoRepository(Protocol):
    def create_project(self, project: Project) -> Project:
        ...

    def get_project(self, project_id: str) -> Project | None:
        ...

    def list_projects(self, *, status: ProjectStatus | None = None) -> tuple[Project, ...]:
        ...

    def update_project(self, project: Project) -> Project:
        ...

    def delete_project(self, project_id: str) -> bool:
        ...

    def create_task(self, task: Task) -> Task:
        ...

    def get_task(self, task_id: str) -> Task | None:
        ...

    def list_tasks(self) -> tuple[Task, ...]:
        ...

    def list_tasks_for_project(self, project_id: str) -> tuple[Task, ...]:
        ...

    def update_task(self, task: Task) -> Task:
        ...

    def delete_task(self, task_id: str) -> bool:
        ...

    def list_inbox(self) -> tuple[Task, ...]:
        ...

    def list_unfinished(self) -> tuple[Task, ...]:
        ...

    def list_today_tasks(self, today: date) -> tuple[tuple[Task, ...], tuple[Task, ...]]:
        ...

    def list_upcoming(self, today: date) -> tuple[Task, ...]:
        ...

    def list_completed(self) -> tuple[Task, ...]:
        ...

    def list_project_overviews(self) -> tuple[ProjectOverview, ...]:
        ...

    def create_proposal(self, proposal: PlanProposal) -> PlanProposal:
        ...

    def get_proposal(self, proposal_id: str) -> PlanProposal | None:
        ...

    def accept_proposal(self, proposal_id: str, *, decided_at: datetime) -> PlanProposal:
        ...

    def reject_proposal(self, proposal_id: str, *, decided_at: datetime) -> PlanProposal:
        ...


class TodoPlannerPort(Protocol):
    def plan_day(self, context: PlannerContext) -> PlannerResult:
        ...
