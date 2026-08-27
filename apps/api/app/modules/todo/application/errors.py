class TodoError(Exception):
    code = "todo_error"


class TodoNotFoundError(TodoError):
    code = "todo_not_found"


class TodoValidationError(TodoError):
    code = "todo_validation_error"


class TodoConflictError(TodoError):
    code = "todo_conflict"


class TodoPlannerUnavailableError(TodoError):
    code = "todo_planner_unavailable"


class TodoPlannerError(TodoError):
    code = "todo_planner_failed"
