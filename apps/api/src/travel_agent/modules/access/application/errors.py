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
