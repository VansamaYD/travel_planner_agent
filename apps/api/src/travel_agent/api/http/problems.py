from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from travel_agent.modules.access.application.errors import (
    AccessError,
    AlreadyInitializedError,
    AuthenticationRequiredError,
    CsrfMismatchError,
    InvalidCredentialsError,
    InvalidInputError,
    LoginRateLimitedError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceNotFoundError,
    VersionConflictError,
)

_STATUS_BY_ERROR: dict[type[AccessError], int] = {
    AlreadyInitializedError: 409,
    AuthenticationRequiredError: 401,
    InvalidCredentialsError: 401,
    CsrfMismatchError: 403,
    PermissionDeniedError: 403,
    InvalidInputError: 422,
    LoginRateLimitedError: 429,
    ResourceNotFoundError: 404,
    ResourceConflictError: 409,
    VersionConflictError: 409,
}


async def access_error_handler(request: Request, error: AccessError) -> JSONResponse:
    status_code = _STATUS_BY_ERROR.get(type(error), 400)
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": _title(error),
            "status": status_code,
            "code": error.code,
            "detail": _detail(error),
            "instance": request.url.path,
            "request_id": request_id,
            "retryable": False,
        },
    )


def _title(error: AccessError) -> str:
    titles = {
        "already_initialized": "系统已经初始化",
        "authentication_required": "需要登录",
        "invalid_credentials": "登录失败",
        "csrf_mismatch": "安全令牌无效",
        "permission_denied": "没有操作权限",
        "invalid_input": "输入不符合要求",
        "login_rate_limited": "登录尝试过于频繁",
        "resource_not_found": "资源不存在",
        "resource_conflict": "资源已经存在",
        "version_conflict": "资料已被其他人修改",
    }
    return titles.get(error.code, "请求无法完成")


def _detail(error: AccessError) -> str:
    if isinstance(error, InvalidCredentialsError):
        return "用户名、邮箱或密码不正确。"
    if isinstance(error, InvalidInputError) and str(error):
        return str(error)
    if isinstance(error, LoginRateLimitedError):
        return "请稍后再试。"
    if isinstance(error, VersionConflictError):
        return "请刷新成员资料并确认最新内容后再保存。"
    return _title(error)
