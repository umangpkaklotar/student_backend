"""Student profile routes for the authenticated student."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_student_profile
from app.database.collections import students_collection, users_collection
from app.models.enrollment import serialize_enrollment
from app.models.student import serialize_student
from app.routes.enrollment import _get_latest_student_enrollment
from app.schemas.student import StudentSelfProfileUpdate

router = APIRouter(prefix="/api/student/profile", tags=["Student Profile"])


@router.get("")
async def get_own_profile(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return the authenticated student's own profile and enrollment status."""
    enrollment = await _get_latest_student_enrollment(student["_id"])
    return {
        "student": serialize_student(student),
        "enrollment": serialize_enrollment(enrollment, student) if enrollment else None,
        "enrollment_status": (
            enrollment.get("status")
            if enrollment
            else ("active" if student.get("class_type") else "not_enrolled")
        ),
    }


@router.put("")
async def update_own_safe_profile(
    payload: StudentSelfProfileUpdate,
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Allow student to update only safe contact/personal fields."""
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        enrollment = await _get_latest_student_enrollment(student["_id"])
        return {
            "message": "No profile changes provided.",
            "student": serialize_student(student),
            "enrollment": serialize_enrollment(enrollment, student) if enrollment else None,
        }

    if "name" in updates:
        updates["name"] = updates["name"].strip()
        await users_collection().update_one(
            {"_id": student["user_id"]},
            {"$set": {"name": updates["name"]}},
        )
    if "phone" in updates:
        updates["phone"] = updates["phone"].strip()
    if "address" in updates:
        updates["address"] = updates["address"].strip()

    await students_collection().update_one(
        {"_id": student["_id"]},
        {"$set": updates},
    )
    updated = await students_collection().find_one({"_id": student["_id"]})
    enrollment = await _get_latest_student_enrollment(student["_id"])
    return {
        "message": "Profile updated successfully.",
        "student": serialize_student(updated),
        "enrollment": serialize_enrollment(enrollment, updated) if enrollment else None,
    }
