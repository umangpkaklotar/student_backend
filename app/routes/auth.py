"""Authentication, self-registration with OTP, and password reset routes."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.database.collections import users_collection
from app.models.user import serialize_user
from app.schemas.auth import (
    AdminProfileUpdate,
    ForgotPasswordSendOtpRequest,
    ForgotPasswordVerifyOtpRequest,
    LoginRequest,
    LoginResponse,
    RegisterSendOtpRequest,
    RegisterVerifyOtpRequest,
    ResetPasswordRequest,
)
from app.schemas.otp import ForgotPasswordVerifyResponse, OtpSendResponse
from app.services.auth_service import (
    authenticate_user,
    reset_user_password,
    send_forgot_password_otp,
    send_registration_otp,
    verify_forgot_password_otp,
    verify_registration_otp_and_create_student,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register/send-otp", response_model=OtpSendResponse)
async def register_send_otp(payload: RegisterSendOtpRequest) -> Dict[str, Any]:
    """Send a 6-digit email verification OTP for student registration."""
    return await send_registration_otp(payload)


@router.post("/register/verify-otp", status_code=status.HTTP_201_CREATED)
async def register_verify_otp(payload: RegisterVerifyOtpRequest) -> Dict[str, Any]:
    """Verify the email OTP and complete student registration."""
    return await verify_registration_otp_and_create_student(payload)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate an active student or admin and return a JWT token."""
    return await authenticate_user(payload)


@router.post("/forgot-password/send-otp", response_model=OtpSendResponse)
async def forgot_password_send_otp(
    payload: ForgotPasswordSendOtpRequest,
) -> Dict[str, Any]:
    """Send an OTP for password reset without exposing email existence."""
    return await send_forgot_password_otp(payload.email)


@router.post("/forgot-password/verify-otp", response_model=ForgotPasswordVerifyResponse)
async def forgot_password_verify_otp(
    payload: ForgotPasswordVerifyOtpRequest,
) -> Dict[str, Any]:
    """Verify the forgot-password OTP and return a short-lived reset token."""
    return await verify_forgot_password_otp(payload.email, payload.otp)


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> Dict[str, Any]:
    """Reset the user's password using a verified reset token."""
    return await reset_user_password(payload)


@router.get("/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the authenticated user's account summary."""
    return {"user": serialize_user(current_user)}


@router.put("/profile")
async def update_auth_profile(
    payload: AdminProfileUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update authenticated user's name and optionally password."""
    from fastapi import HTTPException

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
