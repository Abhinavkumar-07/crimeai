"""
FastAPI authentication & authorisation dependencies.
Injected into route handlers via Depends().
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.core.security import TokenType, UserRole, decode_token, has_required_role
from app.db.session import get_db

logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def _extract_token_payload(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict:
    """Decode bearer token and return payload. Raises 401 on failure."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != TokenType.ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
        )
    return payload


class CurrentUser:
    """Minimal user context extracted from JWT — no DB hit required."""
    def __init__(self, user_id: uuid.UUID, role: UserRole) -> None:
        self.user_id = user_id
        self.role = role


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """
    Dependency: extract authenticated user from JWT.
    Raises 401 if token is missing or invalid.
    """
    payload = await _extract_token_payload(credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
        role = UserRole(payload["role"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
        ) from exc

    # Attach to request state for audit logging middleware
    request.state.user_id = str(user_id)
    request.state.user_role = role

    return CurrentUser(user_id=user_id, role=role)


def require_role(minimum_role: UserRole):
    """
    Dependency factory: ensure user has at least minimum_role.

    Usage:
        @router.delete("/", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """
    async def _check(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not has_required_role(current_user.role, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required",
            )
        return current_user
    return _check


# Pre-built role dependencies for convenience
RequireAdmin   = Depends(require_role(UserRole.ADMIN))
RequirePolice  = Depends(require_role(UserRole.POLICE))
RequireAnalyst = Depends(require_role(UserRole.ANALYST))
