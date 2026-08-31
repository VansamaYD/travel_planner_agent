class PlanningError(Exception):
    code = "planning_error"


class PlanningNotFoundError(PlanningError):
    code = "planning_not_found"


class PlanningPermissionDeniedError(PlanningError):
    code = "planning_permission_denied"


class PlanningInvalidInputError(PlanningError):
    code = "planning_invalid_input"


class PlanningProviderUnavailableError(PlanningError):
    code = "planning_provider_unavailable"


class PlanningProviderError(PlanningError):
    code = "planning_provider_error"


class PlanningVersionConflictError(PlanningError):
    code = "planning_version_conflict"
