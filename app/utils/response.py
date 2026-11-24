"""Consistent JSON response helpers."""

from typing import Any, Dict, Optional


def success_response(
    message: str,
    data: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return a consistent JSON envelope for API responses."""
    payload: Dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload
