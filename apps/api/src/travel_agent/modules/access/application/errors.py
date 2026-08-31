class AccessError(Exception):
    code = "access_error"


class AlreadyInitializedError(AccessError):
    code = "already_initialized"


class InvalidCredentialsError(AccessError):
    code = "invalid_credentials"


class InvalidInputError(AccessError):
    code = "invalid_input"


class AuthenticationRequiredError(AccessError):
    code = "authentication_required"


class CsrfMismatchError(AccessError):
    code = "csrf_mismatch"


class PermissionDeniedError(AccessError):
    code = "permission_denied"


class LoginRateLimitedError(AccessError):
    code = "login_rate_limited"


class ResourceNotFoundError(AccessError):
    code = "resource_not_found"


class ResourceConflictError(AccessError):
    code = "resource_conflict"


class VersionConflictError(AccessError):
    code = "version_conflict"


class InvalidInviteError(AccessError):
    code = "invalid_invite"
