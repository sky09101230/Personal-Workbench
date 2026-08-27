class ProjectActivityError(Exception):
    code = "project_activity_error"


class ProjectActivityNotFoundError(ProjectActivityError):
    code = "project_activity_not_found"


class ProjectActivityConflictError(ProjectActivityError):
    code = "project_activity_conflict"


class ProjectActivityValidationError(ProjectActivityError):
    code = "project_activity_validation_error"
