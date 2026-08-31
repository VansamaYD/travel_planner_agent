class TripError(Exception):
    code = "trip_error"


class TripInvalidInputError(TripError):
    code = "trip_invalid_input"


class TripPermissionDeniedError(TripError):
    code = "trip_permission_denied"


class TripNotFoundError(TripError):
    code = "trip_not_found"


class TripVersionConflictError(TripError):
    code = "trip_version_conflict"
