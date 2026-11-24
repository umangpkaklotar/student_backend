"""Student and Admin class enrollment routes."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.core.dependencies import (
    get_current_student_profile,
    parse_object_id,
    require_admin,
)
from app.database.collections import (
    class_enrollments_collection,
    students_collection,
)
from app.models.enrollment import build_enrollment_document, serialize_enrollment
from app.models.student import serialize_student
from app.schemas.enrollment import EnrollmentCreateOrUpdate, EnrollmentRejectRequest
from app.utils.helpers import today_date_str

router = APIRouter(tags=["Class Enrollments"])

DEFAULT_CLASS_FEES = {
    "karate": 1000.0,
    "skating": 1000.0,
}


async def _get_latest_student_enrollment(student_oid: ObjectId) -> Optional[Dict[str, Any]]:
    """Return active enrollment first, else pending, else most recent rejected enrollment."""
    active = await class_enrollments_collection().find_one(
        {"student_id": student_oid, "status": "active"}
    )
    if active:
        return active
    pending = await class_enrollments_collection().find_one(
        {"student_id": student_oid, "status": "pending"}
    )
    if pending:
        return pending
    docs = (
        await class_enrollments_collection()
        .find({"student_id": student_oid})
        .sort("created_at", -1)
        .to_list(length=1)
    )
    return docs[0] if docs else None


# ==========================================
# Student Enrollment Endpoints
# ==========================================


@router.get("/api/student/enrollment")
async def get_my_enrollment(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Get the logged-in student's current class enrollment status."""
    enrollment = await _get_latest_student_enrollment(student["_id"])
    return {
        "student": serialize_student(student),
        "enrollment": serialize_enrollment(enrollment, student) if enrollment else None,
        "has_active_class": bool(
            enrollment and enrollment.get("status") == "active" and student.get("class_type")
        ),
    }


@router.post("/api/student/enrollment", status_code=status.HTTP_201_CREATED)
async def submit_my_enrollment(
    payload: EnrollmentCreateOrUpdate,
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Submit a class enrollment form (Karate or Skating) for admin approval."""
    existing_active = await class_enrollments_collection().find_one(
        {"student_id": student["_id"], "status": "active"}
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an active {existing_active['class_type']} enrollment.",
        )

    existing_pending = await class_enrollments_collection().find_one(
        {"student_id": student["_id"], "status": "pending"}
    )
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending enrollment awaiting admin approval.",
        )

    # Optionally update student's safe contact fields if edited in enrollment form
    student_updates: Dict[str, Any] = {}
    if payload.phone:
        student_updates["phone"] = payload.phone.strip()
    if payload.address:
        student_updates["address"] = payload.address.strip()
    if payload.date_of_birth:
        student_updates["date_of_birth"] = payload.date_of_birth
    if student_updates:
        await students_collection().update_one(
            {"_id": student["_id"]},
            {"$set": student_updates},
        )
        student = await students_collection().find_one({"_id": student["_id"]})

    enrollment_data = {
        "emergency_contact_name": payload.emergency_contact_name.strip(),
        "emergency_contact_number": payload.emergency_contact_number.strip(),
        "previous_experience": payload.previous_experience.strip() or "None",
        "preferred_batch": payload.preferred_batch.strip(),
    }

    doc = build_enrollment_document(
        student_oid=student["_id"],
        class_type=payload.class_type,
        enrollment_data=enrollment_data,
    )
    res = await class_enrollments_collection().insert_one(doc)
    created = await class_enrollments_collection().find_one({"_id": res.inserted_id})

    return {
        "message": "Enrollment submitted successfully.",
        "enrollment": serialize_enrollment(created, student),
    }


@router.put("/api/student/enrollment")
async def update_my_enrollment(
    payload: EnrollmentCreateOrUpdate,
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Update a pending enrollment or resubmit after rejection (never overwrites an active class)."""
    existing_active = await class_enrollments_collection().find_one(
        {"student_id": student["_id"], "status": "active"}
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active class enrollment cannot be changed directly. Contact the academy.",
        )

    latest = await _get_latest_student_enrollment(student["_id"])
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No enrollment found to update. Please submit a new enrollment.",
        )

    enrollment_data = {
        "emergency_contact_name": payload.emergency_contact_name.strip(),
        "emergency_contact_number": payload.emergency_contact_number.strip(),
        "previous_experience": payload.previous_experience.strip() or "None",
        "preferred_batch": payload.preferred_batch.strip(),
    }

    await class_enrollments_collection().update_one(
        {"_id": latest["_id"]},
        {
            "$set": {
                "class_type": payload.class_type.lower(),
                "enrollment_data": enrollment_data,
                "status": "pending",
                "rejection_reason": None,
                "approved_at": None,
            }
        },
    )
    updated = await class_enrollments_collection().find_one({"_id": latest["_id"]})
    return {
        "message": "Enrollment updated successfully.",
        "enrollment": serialize_enrollment(updated, student),
    }


# ==========================================
# Admin Enrollment Management Endpoints
# ==========================================


@router.get("/api/admin/enrollments")
async def list_admin_enrollments(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    class_type: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """List all student class enrollments for Admin review."""
    query: Dict[str, Any] = {}
    if status_filter and status_filter.lower() in {"pending", "active", "rejected"}:
        query["status"] = status_filter.lower()
    if class_type and class_type.lower() in {"karate", "skating"}:
        query["class_type"] = class_type.lower()

    docs = (
        await class_enrollments_collection()
        .find(query)
        .sort("created_at", -1)
        .to_list(length=2000)
    )
    student_oids = list({doc["student_id"] for doc in docs})
    student_map: Dict[ObjectId, Dict[str, Any]] = {}
    if student_oids:
        async for s_doc in students_collection().find({"_id": {"$in": student_oids}}):
            student_map[s_doc["_id"]] = s_doc

    enrollments: List[Dict[str, Any]] = [
        serialize_enrollment(doc, student_map.get(doc["student_id"])) for doc in docs
    ]
    return {
        "enrollments": enrollments,
        "total": len(enrollments),
        "pending_count": sum(1 for e in enrollments if e["status"] == "pending"),
    }


@router.get("/api/admin/enrollments/{enrollment_id}")
async def get_admin_enrollment_detail(
    enrollment_id: str,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Get details for a specific enrollment (Admin only)."""
    enr_oid = parse_object_id(enrollment_id, "enrollment_id")
    doc = await class_enrollments_collection().find_one({"_id": enr_oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found.",
        )
    student = await students_collection().find_one({"_id": doc["student_id"]})
    return {"enrollment": serialize_enrollment(doc, student)}


@router.put("/api/admin/enrollments/{enrollment_id}/approve")
async def approve_enrollment(
    enrollment_id: str,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Approve a class enrollment and activate the student's class (Admin only)."""
    enr_oid = parse_object_id(enrollment_id, "enrollment_id")
    enrollment = await class_enrollments_collection().find_one({"_id": enr_oid})
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found.",
        )

    student = await students_collection().find_one({"_id": enrollment["student_id"]})
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found.",
        )

    other_active = await class_enrollments_collection().find_one(
        {
            "student_id": student["_id"],
            "status": "active",
            "_id": {"$ne": enr_oid},
        }
    )
    if other_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Student already has an active {other_active['class_type']} enrollment.",
        )

    now_utc = datetime.now(timezone.utc)
    class_type = enrollment["class_type"].lower()
    await class_enrollments_collection().update_one(
        {"_id": enr_oid},
        {
            "$set": {
                "status": "active",
                "approved_at": now_utc,
                "rejection_reason": None,
            }
        },
    )

    student_updates: Dict[str, Any] = {
        "class_type": class_type,
        "status": "active",
    }
    if not student.get("joining_date"):
        student_updates["joining_date"] = today_date_str()
    if not student.get("monthly_fee") or float(student.get("monthly_fee", 0)) <= 0:
        student_updates["monthly_fee"] = DEFAULT_CLASS_FEES.get(class_type, 1000.0)

    await students_collection().update_one(
        {"_id": student["_id"]},
        {"$set": student_updates},
    )

    updated_enrollment = await class_enrollments_collection().find_one({"_id": enr_oid})
    updated_student = await students_collection().find_one({"_id": student["_id"]})
    return {
        "message": "Enrollment approved successfully.",
        "enrollment": serialize_enrollment(updated_enrollment, updated_student),
        "student": serialize_student(updated_student),
    }


@router.put("/api/admin/enrollments/{enrollment_id}/reject")
async def reject_enrollment(
    enrollment_id: str,
    payload: Optional[EnrollmentRejectRequest] = Body(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Reject a class enrollment (Admin only)."""
    enr_oid = parse_object_id(enrollment_id, "enrollment_id")
    enrollment = await class_enrollments_collection().find_one({"_id": enr_oid})
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found.",
        )

    reason = payload.reason.strip() if payload and payload.reason else None
    await class_enrollments_collection().update_one(
        {"_id": enr_oid},
        {
            "$set": {
                "status": "rejected",
                "approved_at": None,
                "rejection_reason": reason,
            }
        },
    )

    # If the rejected enrollment was previously the active one, clear class_type on student
    student = await students_collection().find_one({"_id": enrollment["student_id"]})
    if student and enrollment.get("status") == "active":
        await students_collection().update_one(
            {"_id": student["_id"]},
            {"$set": {"class_type": None}},
        )
        student = await students_collection().find_one({"_id": student["_id"]})

    updated_enrollment = await class_enrollments_collection().find_one({"_id": enr_oid})
    return {
        "message": "Enrollment rejected.",
        "enrollment": serialize_enrollment(updated_enrollment, student),
    }
