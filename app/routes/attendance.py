"""Attendance management routes."""

from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import (
    get_current_user,
    parse_object_id,
    require_admin,
)
from app.database.collections import attendance_collection, students_collection
from app.models.attendance import build_attendance_document, serialize_attendance
from app.models.student import serialize_student
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate
from app.utils.helpers import (
    calculate_attendance_summary,
    current_month_str,
    resolve_student,
    validate_date_str,
    validate_month_str,
)

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def mark_attendance(
    payload: AttendanceCreate,
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Mark attendance for one or multiple students on a given date (Admin only)."""
    date_str = validate_date_str(payload.date)
    class_type = payload.class_type.lower()

    entries = list(payload.records or [])
    if payload.student_id and payload.status:
        entries.append(
            type("Entry", (), {"student_id": payload.student_id, "status": payload.status})()
        )

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one attendance record is required.",
        )

    resolved_items: List[tuple[Dict[str, Any], str]] = []
    seen_oids: set[ObjectId] = set()
    for entry in entries:
        student = await resolve_student(entry.student_id)
        if student["class_type"] != class_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student {student['student_id']} belongs to {student['class_type']} class, not {class_type}.",
            )
        if student["_id"] in seen_oids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate attendance entry in request for student {student['student_id']}.",
            )
        seen_oids.add(student["_id"])
        resolved_items.append((student, entry.status.lower()))

    existing_cursor = attendance_collection().find(
        {"student_id": {"$in": list(seen_oids)}, "date": date_str}
    )
    existing_docs = await existing_cursor.to_list(length=len(seen_oids))
    if existing_docs:
        existing_oids = {doc["student_id"] for doc in existing_docs}
        dup_codes = [
            student["student_id"]
            for student, _ in resolved_items
            if student["_id"] in existing_oids
        ]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate attendance: already marked on {date_str} for {', '.join(dup_codes)}.",
        )

    docs_to_insert = [
        build_attendance_document(
            student_oid=student["_id"],
            date_str=date_str,
            class_type=class_type,
            status_val=status_val,
            marked_by=admin_user["_id"],
        )
        for student, status_val in resolved_items
    ]

    try:
        insert_res = await attendance_collection().insert_many(docs_to_insert)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate attendance record for date {date_str}.",
        ) from exc

    student_map = {student["_id"]: student for student, _ in resolved_items}
    inserted_cursor = attendance_collection().find(
        {"_id": {"$in": insert_res.inserted_ids}}
    )
    created_records: List[Dict[str, Any]] = []
    async for rec in inserted_cursor:
        created_records.append(serialize_attendance(rec, student_map.get(rec["student_id"])))

    return {
        "message": f"Attendance marked for {len(created_records)} student(s).",
        "records": created_records,
    }


@router.get("/student/{student_id}")
async def get_student_attendance(
    student_id: str,
    month: Optional[str] = Query(default=None, description="Filter by YYYY-MM"),
    start_date: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """View attendance history and summary for a student (Admin or own Student)."""
    student = await resolve_student(student_id)
    if current_user.get("role") != "admin" and student["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view another student's attendance.",
        )

    query: Dict[str, Any] = {"student_id": student["_id"]}
    if month:
        valid_month = validate_month_str(month)
        query["date"] = {"$regex": f"^{valid_month}-"}
    elif start_date or end_date:
        date_filter: Dict[str, Any] = {}
        if start_date:
            date_filter["$gte"] = validate_date_str(start_date)
        if end_date:
            date_filter["$lte"] = validate_date_str(end_date)
        query["date"] = date_filter

    cursor = attendance_collection().find(query).sort("date", -1)
    docs = await cursor.to_list(length=1000)
    records = [serialize_attendance(doc, student) for doc in docs]
    summary = calculate_attendance_summary(docs)

    return {
        "student": serialize_student(student),
        "records": records,
        "summary": summary,
    }


@router.get("/monthly/{student_id}")
async def get_student_monthly_attendance(
    student_id: str,
    month: Optional[str] = Query(default=None, description="Month in YYYY-MM format"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get monthly attendance statistics and records for a student (Admin or own Student)."""
    student = await resolve_student(student_id)
    if current_user.get("role") != "admin" and student["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view another student's attendance.",
        )

    target_month = validate_month_str(month) if month else current_month_str()
    cursor = attendance_collection().find(
        {
            "student_id": student["_id"],
            "date": {"$regex": f"^{target_month}-"},
        }
    ).sort("date", -1)
    docs = await cursor.to_list(length=100)
    records = [serialize_attendance(doc, student) for doc in docs]
    summary = calculate_attendance_summary(docs)

    return {
        "student": serialize_student(student),
        "month": target_month,
        "records": records,
        **summary,
    }


@router.get("/date/{date}")
async def get_attendance_by_date(
    date: str,
    class_type: Optional[str] = Query(default=None, description="Filter by karate or skating"),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Get all attendance records for a specific date (Admin only)."""
    valid_date = validate_date_str(date)
    query: Dict[str, Any] = {"date": valid_date}
    if class_type and class_type.lower() in {"karate", "skating"}:
        query["class_type"] = class_type.lower()

    cursor = attendance_collection().find(query)
    docs = await cursor.to_list(length=1000)

    student_oids = list({doc["student_id"] for doc in docs})
    student_map: Dict[ObjectId, Dict[str, Any]] = {}
    if student_oids:
        s_cursor = students_collection().find({"_id": {"$in": student_oids}})
        async for s_doc in s_cursor:
            student_map[s_doc["_id"]] = s_doc

    records = [serialize_attendance(doc, student_map.get(doc["student_id"])) for doc in docs]
    summary = calculate_attendance_summary(docs)

    return {
        "date": valid_date,
        "class_type": class_type.lower() if class_type else None,
        "records": records,
        "summary": summary,
    }


@router.put("/{attendance_id}")
async def update_attendance(
    attendance_id: str,
    payload: AttendanceUpdate,
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Update an existing attendance record (Admin only)."""
    att_oid = parse_object_id(attendance_id, "attendance_id")
    existing = await attendance_collection().find_one({"_id": att_oid})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found.",
        )

    await attendance_collection().update_one(
        {"_id": att_oid},
        {"$set": {"status": payload.status.lower(), "marked_by": admin_user["_id"]}},
    )
    updated = await attendance_collection().find_one({"_id": att_oid})
    student = await students_collection().find_one({"_id": updated["student_id"]})

    return {
        "message": "Attendance updated successfully.",
        "record": serialize_attendance(updated, student),
    }
