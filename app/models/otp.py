"""MongoDB document helpers for the otp_verifications collection."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def build_otp_document(
    email: str,
    otp_hash: str,
    expires_at: datetime,
    purpose: str = "register",
    registration_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an OTP verification record with hashed OTP and expiry timestamp."""
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        "email": email.strip().lower(),
        "otp_hash": otp_hash,
        "purpose": purpose,
        "expires_at": expires_at,
        "attempts": 0,
        "verified": False,
        "last_sent_at": now,
        "created_at": now,
    }
    if registration_data is not None:
        doc["registration_data"] = registration_data
    return doc
