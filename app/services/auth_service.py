"""Authentication, self-registration, and password reset service."""

from typing import Any, Dict

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database.collections import students_collection, users_collection
from app.models.student import build_student_document, serialize_student
from app.models.user import build_user_document, serialize_user
from app.schemas.auth import (
    LoginRequest,
    RegisterSendOtpRequest,
    RegisterVerifyOtpRequest,
    ResetPasswordRequest,
)
from app.services.otp_service import issue_otp, verify_otp_code
from app.utils.helpers import generate_next_student_id, today_date_str

DEFAULT_CLASS_FEES = {
    "karate": 1000.0,
    "skating": 1000.0,
}


async def send_registration_otp(payload: RegisterSendOtpRequest) -> Dict[str, Any]:
    """Validate registration payload, prevent duplicate email, and send OTP."""
    email = payload.email.strip().lower()

    existing_user = await users_collection().find_one({"email": email})
    existing_student = await students_collection().find_one({"email": email})
    if existing_user or existing_student:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email is already registered.",
        )

    if payload.resend:
        await issue_otp(
            email=email,
            purpose="register",
            registration_data=None,
            allow_reuse_registration_data=True,
        )
    else:
        reg_data = {
            "name": payload.name.strip(),
            "email": email,
            "phone": payload.phone,
            "password_hash": hash_password(payload.password),
            "gender": payload.gender,
            "date_of_birth": payload.date_of_birth,
            "address": payload.address.strip(),
        }
        await issue_otp(
            email=email,
            purpose="register",
            registration_data=reg_data,
        )

    return {
        "success": True,
        "message": "OTP sent successfully to your email.",
        "email": email,
        "expires_in_seconds": 300,
        "resend_cooldown_seconds": 30,
    }


async def verify_registration_otp_and_create_student(
    payload: RegisterVerifyOtpRequest,
) -> Dict[str, Any]:
    """Verify OTP and create the verified student user and student profile."""
    email = payload.email.strip().lower()

    if await users_collection().find_one({"email": email}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email is already registered.",
        )

    record = await verify_otp_code(email=email, otp=payload.otp, purpose="register")
    reg_data = record.get("registration_data")
    if not reg_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration session expired. Please register again.",
        )

    user_doc = build_user_document(
        name=reg_data["name"],
        email=email,
        hashed_password=reg_data["password_hash"],
        role="student",
        email_verified=True,
        status_val="active",
    )

    try:
        user_result = await users_collection().insert_one(user_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email is already registered.",
        ) from exc

    student_payload = {
        "name": reg_data["name"],
        "email": email,
        "phone": reg_data["phone"],
        "gender": reg_data["gender"],
        "date_of_birth": reg_data["date_of_birth"],
        "address": reg_data["address"],
        "class_type": None,
        "joining_date": None,
        "monthly_fee": 0.0,
    }

    created_student = None
    for _ in range(3):
        student_code = await generate_next_student_id()
        student_doc = build_student_document(
            student_id=student_code,
            user_id=user_result.inserted_id,
            data=student_payload,
        )
        try:
            insert_res = await students_collection().insert_one(student_doc)
            created_student = await students_collection().find_one(
                {"_id": insert_res.inserted_id}
            )
            break
        except DuplicateKeyError as exc:
            if "email" in str(exc):
                await users_collection().delete_one({"_id": user_result.inserted_id})
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email is already registered.",
                ) from exc

    if created_student is None:
        await users_collection().delete_one({"_id": user_result.inserted_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to assign a student ID. Please try again.",
        )

    return {
        "success": True,
        "message": "Email verified successfully. Registration completed successfully.",
        "student": serialize_student(created_student),
    }


async def authenticate_user(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate an existing active user and return a JWT token."""
    email = payload.email.strip().lower()
    user = await users_collection().find_one({"email": email})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    if user.get("status", "active") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive. Please contact the academy.",
        )

    token = create_access_token(
        data={
            "user_id": str(user["_id"]),
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


async def send_forgot_password_otp(email: str) -> Dict[str, Any]:
    """Send password reset OTP without disclosing whether the email is registered."""
    normalized_email = email.strip().lower()
    user = await users_collection().find_one({"email": normalized_email})
    if user:
        await issue_otp(email=normalized_email, purpose="forgot_password")

    return {
        "success": True,
        "message": "If an account with that email exists, an OTP has been sent.",
        "email": normalized_email,
        "expires_in_seconds": 300,
        "resend_cooldown_seconds": 30,
    }


async def verify_forgot_password_otp(email: str, otp: str) -> Dict[str, Any]:
    """Verify forgot-password OTP and issue a short-lived password reset token."""
    normalized_email = email.strip().lower()
    await verify_otp_code(email=normalized_email, otp=otp, purpose="forgot_password")
    reset_token = create_password_reset_token(normalized_email)
    return {
        "success": True,
        "message": "OTP verified. You can now set a new password.",
        "reset_token": reset_token,
    }


async def reset_user_password(payload: ResetPasswordRequest) -> Dict[str, Any]:
    """Verify reset token and update the user's hashed password."""
    decoded = decode_access_token(payload.reset_token)
    if not decoded or decoded.get("purpose") != "password_reset" or not decoded.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset session. Please request a new OTP.",
        )

    email = decoded["email"].strip().lower()
    user = await users_collection().find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )

    await users_collection().update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hash_password(payload.new_password)}},
    )
    return {
        "success": True,
        "message": "Password reset successfully. Please login.",
    }
