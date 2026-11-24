"""Password hashing, OTP hashing, and JWT token utilities."""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Dict, Optional

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def generate_secure_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    upper_bound = 10**length
    return f"{secrets.randbelow(upper_bound):0{length}d}"


def hash_otp(otp: str) -> str:
    """Hash a plain-text OTP using bcrypt so raw OTP is never persisted."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(otp.encode("utf-8"), salt).decode("utf-8")


def verify_otp_hash(plain_otp: str, otp_hash: str) -> bool:
    """Verify a plain-text OTP against its stored hash."""
    try:
        return bcrypt.checkpw(
            plain_otp.encode("utf-8"),
            otp_hash.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token containing user_id, role, and email."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_password_reset_token(email: str) -> str:
    """Create a short-lived signed token after forgot-password OTP verification."""
    return create_access_token(
        data={"email": email.strip().lower(), "purpose": "password_reset"},
        expires_delta=timedelta(minutes=10),
    )


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError:
        return None
