"""
Audit logging middleware.
Every API request by an authenticated user is recorded.
Law-enforcement systems require full audit trails.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger

logger = get_logger(__name__)

# Paths we never audit (health checks, static assets)
_SKIP_PATHS = {"/health", "/ready", "/metrics", "/favicon.ico", "/docs", "/redoc", "/openapi.json"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Records every authenticated request with:
    - request_id (UUID, added to response headers)
    - user identity (extracted from JWT if present)
    - method, path, status, duration
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Attach a unique request ID to every request
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()

        # Extract user identity from state (set by auth dependency later)
        # On first pass it won't be there — that's fine
        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        user_id = getattr(request.state, "user_id", "anonymous")
        user_role = getattr(request.state, "user_role", "none")

        log_level = "warning" if response.status_code >= 400 else "info"
        getattr(logger, log_level)(
            "api_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=str(request.url.query) or None,
            status_code=response.status_code,
            duration_ms=duration_ms,
            user_id=user_id,
            user_role=user_role,
            ip=request.client.host if request.client else None,
        )

        # Propagate request ID to client
        response.headers["X-Request-ID"] = request_id
        return response
