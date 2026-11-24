"""Student management routes (Admin only for CRUD, Student can view own profile)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import get_current_user, require_admin
from app.core.security import hash_password
from app.database.collections import (
    attendance_collection,
    fees_collection,
    students_collection,
    users_collection,
)
from app.models.student import build_student_document, serialize_student
from app.models.user import build_user_document
from app.schemas.student import StudentCreate, StudentUpdate
from app.utils.helpers import generate_next_student_id, resolve_student

router = APIRouter(prefix="/api/students", tags=["Students"])


@router.get("")
async def list_students(
    search: Optional[str] = Query(default=None, description="Search by name, email, phone, or STU ID"),
    class_type: Optional[str] = Query(default=None, description="Filter by karate or skating"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by active or inactive"),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """List all students with optional search and filters (Admin only)."""
    query: Dict[str, Any] = {}
    if class_type and class_type.lower() in {"karate", "skating"}:
        query["class_type"] = class_type.lower()
    if status_filter and status_filter.lower() in {"active", "inactive"}:
        query["status"] = status_filter.lower()
    if search and search.strip():
        regex = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"name": regex},
            {"email": regex},
            {"phone": regex},
            {"student_id": regex},
        ]

    cursor = students_collection().find(query).sort("created_at", -1)
    students: List[Dict[str, Any]] = []
    async for doc in cursor:
        students.append(serialize_student(doc))

    return {"students": students, "total": len(students)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_student(
    payload: StudentCreate,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Create a new student account and profile (Admin only)."""
    email = payload.email.strip().lower()

    existing_user = await users_collection().find_one({"email": email})
    existing_student = await students_collection().find_one({"email": email})
    if existing_user or existing_student:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student with this email already exists.",
        )

    user_doc = build_user_document(
        name=payload.name,
        email=email,
        hashed_password=hash_password(payload.password),
        role="student",
    )

    try:
        user_result = await users_collection().insert_one(user_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student with this email already exists.",
        ) from exc

    student_data = payload.model_dump()
    created_student = None
    for _ in range(3):
        student_code = await generate_next_student_id()
        student_doc = build_student_document(
            student_id=student_code,
            user_id=user_result.inserted_id,
            data=student_data,
        )
        try:
            insert_res = await students_collection().insert_one(student_doc)
            created_student = await students_collection().find_one({"_id": insert_res.inserted_id})
            break
        except DuplicateKeyError as exc:
            if "email" in str(exc):
                await users_collection().delete_one({"_id": user_result.inserted_id})
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Student with this email already exists.",
                ) from exc

    if created_student is None:
        await users_collection().delete_one({"_id": user_result.inserted_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate a unique student ID. Please retry.",
        )

    return {
        "message": "Student created successfully.",
        "student": serialize_student(created_student),
    }


@router.get("/{student_id}")
async def get_student(
    student_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get student details. Admin can view any student; Student can only view themselves."""
    student = await resolve_student(student_id)
    if current_user.get("role") != "admin" and student["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this student profile.",
        )
    return {"student": serialize_student(student)}


@router.put("/{student_id}")
async def update_student(
    student_id: str,
    payload: StudentUpdate,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Update student profile details (Admin only)."""
    student = await resolve_student(student_id)
    updates = payload.model_dump(exclude_none=True)

    if not updates:
        return {
            "message": "No changes provided.",
            "student": serialize_student(student),
        }

    user_updates: Dict[str, Any] = {}
    if "email" in updates:
        new_email = updates["email"].strip().lower()
        updates["email"] = new_email
        if new_email != student["email"]:
            dup_user = await users_collection().find_one({"email": new_email})
            dup_student = await students_collection().find_one({"email": new_email})
            if dup_user or dup_student:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another account with this email already exists.",
                )
            user_updates["email"] = new_email

    if "name" in updates:
        updates["name"] = updates["name"].strip()
        user_updates["name"] = updates["name"]

    if "phone" in updates:
        updates["phone"] = updates["phone"].strip()

    if "address" in updates:
        updates["address"] = updates["address"].strip()

    if "monthly_fee" in updates:
        updates["monthly_fee"] = float(updates["monthly_fee"])

    password_plain = updates.pop("password", None)
    if password_plain:
        user_updates["password"] = hash_password(password_plain)

    if updates:
        await students_collection().update_one(
            {"_id": student["_id"]},
            {"$set": updates},
        )
    if user_updates:
        await users_collection().update_one(
            {"_id": student["user_id"]},
            {"$set": user_updates},
        )

    updated = await students_collection().find_one({"_id": student["_id"]})
    return {
        "message": "Student updated successfully.",
        "student": serialize_student(updated),
    }


@router.delete("/{student_id}")
async def delete_or_deactivate_student(
    student_id: str,
    permanent: bool = Query(default=False, description="Set true to permanently delete student and records"),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Deactivate a student by default, or permanently delete when permanent=true (Admin only)."""
    student = await resolve_student(student_id)

    if permanent:
        await attendance_collection().delete_many({"student_id": student["_id"]})
        await fees_collection().delete_many({"student_id": student["_id"]})
        await students_collection().delete_one({"_id": student["_id"]})
        await users_collection().delete_one({"_id": student["user_id"]})
        return {
            "message": "Student permanently deleted.",
            "student_id": student["student_id"],
            "deleted": True,
        }

    await students_collection().update_one(
        {"_id": student["_id"]},
        {"$set": {"status": "inactive"}},
    )
    updated = await students_collection().find_one({"_id": student["_id"]})
    return {
        "message": "Student deactivated successfully.",
        "student": serialize_student(updated),
        "deleted": False,
    }
