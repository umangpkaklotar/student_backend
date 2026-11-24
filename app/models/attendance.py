"""MongoDB document helpers for the attendance collection."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from bson import ObjectId


def serialize_attendance(
    record: Dict[str, Any],
    student: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert a MongoDB attendance document into an API-safe dictionary."""
    result = {
        "id": str(record["_id"]),
        "student_id": str(record["student_id"]),
        "date": record["date"],
        "class_type": record["class_type"],
        "status": record["status"],
        "marked_by": str(record["marked_by"]),
        "created_at": record["created_at"].isoformat()
        if isinstance(record.get("created_at"), datetime)
        else record.get("created_at"),
    }
    if student is not None:
        result["student_code"] = student.get("student_id")
        result["student_name"] = student.get("name")
    return result


def build_attendance_document(
    student_oid: ObjectId,
    date_str: str,
    class_type: str,
    status_val: str,
    marked_by: ObjectId,
) -> Dict[str, Any]:
    """Build an attendance document for insertion into MongoDB."""
    return {
        "student_id": student_oid,
        "date": date_str,
        "class_type": class_type.lower(),
        "status": status_val.lower(),
        "marked_by": marked_by,
        "created_at": datetime.now(timezone.utc),
    }
