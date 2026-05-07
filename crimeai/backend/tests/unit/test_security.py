"""Unit tests for security module."""
import pytest
from jose import JWTError

from app.core.security import (
    UserRole,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    has_required_role,
    verify_password,
)


def test_password_hash_and_verify():
    plain = "SecurePass1"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("WrongPass", hashed)


def test_access_token_roundtrip():
    token = create_access_token(subject="user-123", role=UserRole.POLICE)
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == UserRole.POLICE
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token(subject="user-456", role=UserRole.ADMIN)
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"


def test_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_role_hierarchy():
    assert has_required_role(UserRole.ADMIN, UserRole.POLICE)
    assert has_required_role(UserRole.ADMIN, UserRole.ADMIN)
    assert not has_required_role(UserRole.POLICE, UserRole.ADMIN)
    assert has_required_role(UserRole.POLICE, UserRole.ANALYST)
    assert not has_required_role(UserRole.READONLY, UserRole.POLICE)
