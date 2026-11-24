"""MongoDB document helpers for the class_enrollments collection."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from bson import ObjectId


def serialize_enrollment(
    enrollment: Dict[str, Any],
    student: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert a MongoDB class_enrollment document into an API-safe dictionary."""
    result: Dict[str, Any] = {
        "id": str(enrollment["_id"]),
        "student_id": str(enrollment["student_id"]),
        "class_type": enrollment["class_type"],
        "enrollment_data": enrollment.get("enrollment_data", {}),
        "status": enrollment.get("status", "pending"),
        "rejection_reason": enrollment.get("rejection_reason"),
        "created_at": enrollment["created_at"].isoformat()
        if isinstance(enrollment.get("created_at"), datetime)
        else enrollment.get("created_at"),
        "approved_at": enrollment["approved_at"].isoformat()
        if isinstance(enrollment.get("approved_at"), datetime)
        else enrollment.get("approved_at"),
    }
    if student is not None:
        result["student_code"] = student.get("student_id")
        result["student_name"] = student.get("name")
        result["student_email"] = student.get("email")
        result["student_phone"] = student.get("phone")
        result["date_of_birth"] = student.get("date_of_birth")
        result["address"] = student.get("address")
    return result


def build_enrollment_document(
    student_oid: ObjectId,
    class_type: str,
    enrollment_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a new pending class enrollment document."""
    return {
        "student_id": student_oid,
        "class_type": class_type.lower(),
        "enrollment_data": enrollment_data,
        "status": "pending",
        "rejection_reason": None,
        "created_at": datetime.now(timezone.utc),
        "approved_at": None,
    }
