"""User management endpoints (Admin only)."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_role
from app.core.security import UserRole
from app.db.session import get_db
from app.repositories.user_repository import UserRepository

router = APIRouter()


@router.get("/", summary="List all users (Admin)")
async def list_users(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    repo = UserRepository(db)
    users = await repo.list_all(limit=limit, offset=offset)
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "badge_number": u.badge_number,
            "department": u.department,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/me", summary="Get current user profile")
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "badge_number": user.badge_number,
        "department": user.department,
    }


@router.delete("/{user_id}", summary="Deactivate user (Admin)")
async def deactivate_user(
    user_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(current_user.user_id):
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    await repo.deactivate(user_id)
    return {"message": "User deactivated", "user_id": str(user_id)}
