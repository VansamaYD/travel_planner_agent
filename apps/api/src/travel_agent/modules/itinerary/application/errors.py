class ItineraryError(Exception):
    code = "itinerary_error"


class ItineraryNotFoundError(ItineraryError):
    code = "itinerary_not_found"


class ItineraryInvalidInputError(ItineraryError):
    code = "itinerary_invalid_input"


class ItineraryPermissionDeniedError(ItineraryError):
    code = "itinerary_permission_denied"


class ItineraryVersionConflictError(ItineraryError):
    code = "itinerary_version_conflict"
