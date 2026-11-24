"""Authentication routes."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database.collections import users_collection
from app.models.user import serialize_user
from app.schemas.auth import AdminProfileUpdate, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate an admin or student and return a JWT access token."""
    email = payload.email.strip().lower()
    user = await users_collection().find_one({"email": email})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(
        data={
            "sub": str(user["_id"]),
            "email": user["email"],
            "role": user["role"],
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user": serialize_user(user),
    }


@router.get("/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return currently authenticated user profile."""
    return {"user": serialize_user(current_user)}


@router.put("/profile")
async def update_profile(
    payload: AdminProfileUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update authenticated user's name and optionally password."""
    update_fields: Dict[str, Any] = {"name": payload.name.strip()}

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required to set a new password.",
            )
        if not verify_password(payload.current_password, current_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        update_fields["password"] = hash_password(payload.new_password)

    await users_collection().update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )
    updated = await users_collection().find_one({"_id": current_user["_id"]})
    return {
        "message": "Profile updated successfully.",
        "user": serialize_user(updated),
    }
