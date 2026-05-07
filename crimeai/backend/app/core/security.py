"""
Security utilities: JWT creation/verification, password hashing, RBAC helpers.
All crypto operations live here — never scattered across the codebase.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# bcrypt context — auto-upgrades old hashes on login
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(StrEnum):
    ADMIN = "admin"
    POLICE = "police"
    ANALYST = "analyst"
    READONLY = "readonly"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.READONLY: 0,
    UserRole.ANALYST: 1,
    UserRole.POLICE: 2,
    UserRole.ADMIN: 3,
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str | int,
    role: UserRole,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": TokenType.ACCESS,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int, role: UserRole) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": TokenType.REFRESH,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT. Raises JWTError on failure.
    Caller is responsible for handling the exception.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        logger.warning("jwt_decode_failed", error=str(exc))
        raise


def has_required_role(user_role: UserRole, required_role: UserRole) -> bool:
    """Check if user_role meets or exceeds required_role in the hierarchy."""
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(required_role, 999)
