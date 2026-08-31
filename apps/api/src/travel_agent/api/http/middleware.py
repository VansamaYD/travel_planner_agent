from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestIdMiddleware:
    """Small ASGI middleware that does not buffer streaming responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_request_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = raw_request_id[:128] if raw_request_id else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)
