"""
Global exception handler middleware.
Converts domain exceptions → structured HTTP responses.
Never leaks stack traces to clients in production.
"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
    CrimeAIError,
    DatabaseError,
    MLServiceError,
    NLPServiceError,
    NotFoundError,
    RateLimitError,
    StorageError,
    ValidationError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Map domain exception → (HTTP status, error code string)
_EXCEPTION_MAP: dict[type[CrimeAIError], tuple[int, str]] = {
    NotFoundError:       (status.HTTP_404_NOT_FOUND,             "not_found"),
    AlreadyExistsError:  (status.HTTP_409_CONFLICT,              "already_exists"),
    AuthenticationError: (status.HTTP_401_UNAUTHORIZED,          "authentication_failed"),
    AuthorizationError:  (status.HTTP_403_FORBIDDEN,             "forbidden"),
    ValidationError:     (status.HTTP_422_UNPROCESSABLE_ENTITY,  "validation_error"),
    RateLimitError:      (status.HTTP_429_TOO_MANY_REQUESTS,     "rate_limit_exceeded"),
    DatabaseError:       (status.HTTP_503_SERVICE_UNAVAILABLE,   "database_error"),
    MLServiceError:      (status.HTTP_503_SERVICE_UNAVAILABLE,   "ml_service_error"),
    NLPServiceError:     (status.HTTP_503_SERVICE_UNAVAILABLE,   "nlp_service_error"),
    StorageError:        (status.HTTP_503_SERVICE_UNAVAILABLE,   "storage_error"),
}


def _error_response(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
    detail: object = None,
) -> JSONResponse:
    body: dict = {
        "error": error_code,
        "message": message,
        "path": str(request.url.path),
    }
    # Only include detail in non-production environments
    if detail and not settings.is_production:
        body["detail"] = detail

    return JSONResponse(status_code=status_code, content=body)


async def domain_exception_handler(request: Request, exc: CrimeAIError) -> JSONResponse:
    status_code, error_code = _EXCEPTION_MAP.get(
        type(exc),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error"),
    )
    logger.warning(
        "domain_exception",
        error_code=error_code,
        message=exc.message,
        path=str(request.url.path),
        method=request.method,
    )
    return _error_response(request, status_code, error_code, exc.message, exc.detail)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=str(request.url.path),
        method=request.method,
        exc_info=True,
    )
    message = "An internal error occurred"
    detail = str(exc) if not settings.is_production else None
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        message,
        detail,
    )
