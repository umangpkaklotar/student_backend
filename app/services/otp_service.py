"""OTP generation, hashed storage, cooldown, expiry, and verification service."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.security import generate_secure_otp, hash_otp, verify_otp_hash
from app.database.collections import otp_verifications_collection
from app.models.otp import build_otp_document
from app.services.email_service import send_otp_email


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def issue_otp(
    email: str,
    purpose: str,
    registration_data: Optional[Dict[str, Any]] = None,
    allow_reuse_registration_data: bool = False,
) -> None:
    """Create and email a fresh 6-digit OTP while enforcing cooldown and invalidating old OTPs."""
    settings = get_settings()
    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)

    existing = await otp_verifications_collection().find_one(
        {"email": normalized_email, "purpose": purpose}
    )

    if existing and not existing.get("verified", False):
        last_sent = existing.get("last_sent_at") or existing.get("created_at")
        if isinstance(last_sent, datetime):
            elapsed = (now - _ensure_utc(last_sent)).total_seconds()
            if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
                wait_seconds = max(1, int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {wait_seconds} seconds before requesting a new OTP.",
                )

    resolved_reg_data = registration_data
    if resolved_reg_data is None and allow_reuse_registration_data:
        if existing and existing.get("registration_data"):
            resolved_reg_data = existing["registration_data"]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending registration found for this email. Please complete the registration form.",
            )

    otp = generate_secure_otp(6)
    otp_hash = hash_otp(otp)
    expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    # Send email before finalizing replacement, or replace record and send
    await send_otp_email(normalized_email, otp, purpose=purpose)

    # Invalidate any prior OTP for this email & purpose by deleting and inserting the fresh record
    await otp_verifications_collection().delete_many(
        {"email": normalized_email, "purpose": purpose}
    )
    new_doc = build_otp_document(
        email=normalized_email,
        otp_hash=otp_hash,
        expires_at=expires_at,
        purpose=purpose,
        registration_data=resolved_reg_data,
    )
    await otp_verifications_collection().insert_one(new_doc)


async def verify_otp_code(
    email: str,
    otp: str,
    purpose: str,
) -> Dict[str, Any]:
    """Validate an OTP against expiry, max attempts, and hash, then invalidate it."""
    settings = get_settings()
    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)

    record = await otp_verifications_collection().find_one(
        {"email": normalized_email, "purpose": purpose, "verified": False}
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found. Please request a new OTP.",
        )

    expires_at = record.get("expires_at")
    if isinstance(expires_at, datetime) and _ensure_utc(expires_at) < now:
        await otp_verifications_collection().delete_one({"_id": record["_id"]})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new OTP.",
        )

    attempts = int(record.get("attempts", 0))
    if attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed OTP attempts. Please request a new OTP.",
        )

    if not verify_otp_hash(otp.strip(), record["otp_hash"]):
        new_attempts = attempts + 1
        await otp_verifications_collection().update_one(
            {"_id": record["_id"]},
            {"$set": {"attempts": new_attempts}},
        )
        remaining = max(0, settings.OTP_MAX_ATTEMPTS - new_attempts)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed OTP attempts. Please request a new OTP.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
        )

    # Invalidate OTP immediately after successful verification
    await otp_verifications_collection().update_one(
        {"_id": record["_id"]},
        {"$set": {"verified": True}, "$unset": {"registration_data": ""}},
    )
    return record
