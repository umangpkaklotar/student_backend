"""MongoDB document helpers for the users collection."""

from datetime import datetime, timezone
from typing import Any, Dict


def serialize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a MongoDB user document into a safe API dictionary."""
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user["created_at"].isoformat()
        if isinstance(user.get("created_at"), datetime)
        else user.get("created_at"),
    }


def build_user_document(
    name: str,
    email: str,
    hashed_password: str,
    role: str,
) -> Dict[str, Any]:
    """Build a new user document for insertion into MongoDB."""
    return {
        "name": name.strip(),
        "email": email.strip().lower(),
        "password": hashed_password,
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }
