"""MongoDB document helpers for the students collection."""

from datetime import datetime, timezone
from typing import Any, Dict
from bson import ObjectId


def serialize_student(student: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a MongoDB student document into an API-safe dictionary."""
    return {
        "id": str(student["_id"]),
        "student_id": student["student_id"],
        "user_id": str(student["user_id"]),
        "name": student["name"],
        "email": student["email"],
        "phone": student["phone"],
        "gender": student["gender"],
        "date_of_birth": student["date_of_birth"],
        "address": student["address"],
        "class_type": student["class_type"],
        "joining_date": student["joining_date"],
        "monthly_fee": float(student["monthly_fee"]),
        "status": student["status"],
        "created_at": student["created_at"].isoformat()
        if isinstance(student.get("created_at"), datetime)
        else student.get("created_at"),
    }


def build_student_document(
    student_id: str,
    user_id: ObjectId,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a new student document for insertion into MongoDB."""
    return {
        "student_id": student_id,
        "user_id": user_id,
        "name": data["name"].strip(),
        "email": data["email"].strip().lower(),
        "phone": data["phone"].strip(),
        "gender": data["gender"].strip(),
        "date_of_birth": data["date_of_birth"],
        "address": data["address"].strip(),
        "class_type": data["class_type"].lower(),
        "joining_date": data["joining_date"],
        "monthly_fee": float(data["monthly_fee"]),
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
