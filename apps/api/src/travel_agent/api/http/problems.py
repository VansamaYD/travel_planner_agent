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
    InvalidInviteError,
    LoginRateLimitedError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceNotFoundError,
    VersionConflictError,
)
from travel_agent.modules.conversations.service import (
    ConversationError,
    ConversationNotFoundError,
    ConversationPermissionError,
)
from travel_agent.modules.itinerary.application.errors import (
    ItineraryError,
    ItineraryInvalidInputError,
    ItineraryNotFoundError,
    ItineraryPermissionDeniedError,
    ItineraryVersionConflictError,
)
from travel_agent.modules.knowledge.domain import KnowledgeError, VisionUnavailableError
from travel_agent.modules.planning.application.errors import (
    PlanningError,
    PlanningInvalidInputError,
    PlanningNotFoundError,
    PlanningPermissionDeniedError,
    PlanningProviderError,
    PlanningProviderUnavailableError,
    PlanningVersionConflictError,
)
from travel_agent.modules.trips.application.errors import (
    TripError,
    TripInvalidInputError,
    TripNotFoundError,
    TripPermissionDeniedError,
    TripVersionConflictError,
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
    InvalidInviteError: 400,
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


async def trip_error_handler(request: Request, error: TripError) -> JSONResponse:
    status_by_error: dict[type[TripError], int] = {
        TripInvalidInputError: 422,
        TripPermissionDeniedError: 403,
        TripNotFoundError: 404,
        TripVersionConflictError: 409,
    }
    details = {
        "trip_permission_denied": "没有查看或修改这趟旅行的权限。",
        "trip_not_found": "旅行不存在或已经删除。",
        "trip_version_conflict": "旅行已经被其他人修改，请刷新后再保存。",  # noqa: RUF001
    }
    status_code = status_by_error.get(type(error), 400)
    detail = str(error) or details.get(error.code, "旅行请求无法完成。")
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": "旅行请求无法完成",
            "status": status_code,
            "code": error.code,
            "detail": detail,
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "retryable": isinstance(error, TripVersionConflictError),
        },
    )


async def itinerary_error_handler(request: Request, error: ItineraryError) -> JSONResponse:
    status_by_error: dict[type[ItineraryError], int] = {
        ItineraryInvalidInputError: 422,
        ItineraryPermissionDeniedError: 403,
        ItineraryNotFoundError: 404,
        ItineraryVersionConflictError: 409,
    }
    details = {
        "itinerary_not_found": "旅行尚未建立正式日程。",
        "itinerary_permission_denied": "没有查看或编辑这份旅行计划的权限。",
        "itinerary_version_conflict": "旅行计划已被其他人修改，请刷新后再保存。",  # noqa: RUF001
    }
    status_code = status_by_error.get(type(error), 400)
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": "旅行计划请求无法完成",
            "status": status_code,
            "code": error.code,
            "detail": str(error) or details.get(error.code, "旅行计划请求无法完成。"),
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "retryable": isinstance(error, ItineraryVersionConflictError),
        },
    )


async def planning_error_handler(request: Request, error: PlanningError) -> JSONResponse:
    status_by_error: dict[type[PlanningError], int] = {
        PlanningInvalidInputError: 422,
        PlanningPermissionDeniedError: 403,
        PlanningNotFoundError: 404,
        PlanningProviderUnavailableError: 503,
        PlanningProviderError: 502,
        PlanningVersionConflictError: 409,
    }
    status_code = status_by_error.get(type(error), 400)
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": "智能规划请求无法完成",
            "status": status_code,
            "code": error.code,
            "detail": str(error) or "智能规划请求无法完成。",
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "retryable": isinstance(error, (PlanningProviderError, PlanningVersionConflictError)),
        },
    )


async def conversation_error_handler(request: Request, error: ConversationError) -> JSONResponse:
    status_by_error: dict[type[ConversationError], int] = {
        ConversationPermissionError: 403,
        ConversationNotFoundError: 404,
    }
    status_code = status_by_error.get(type(error), 422)
    details = {
        "conversation_permission_denied": "没有访问这个对话的权限。",
        "conversation_not_found": "对话不存在。",
    }
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": "对话请求无法完成",
            "status": status_code,
            "code": error.code,
            "detail": str(error) or details.get(error.code, "对话请求无法完成。"),
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "retryable": False,
        },
    )


async def knowledge_error_handler(request: Request, error: KnowledgeError) -> JSONResponse:
    status_code = 503 if isinstance(error, VisionUnavailableError) else 422
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://travel-agent.local/problems/{error.code.replace('_', '-')}",
            "title": "知识库请求无法完成",
            "status": status_code,
            "code": error.code,
            "detail": str(error) or "知识库请求无法完成。",
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "retryable": isinstance(error, VisionUnavailableError),
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
        "invalid_invite": "邀请码无效",
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
    if isinstance(error, InvalidInviteError):
        return "邀请码无效、已过期、已撤销或已被使用。"
    return _title(error)
