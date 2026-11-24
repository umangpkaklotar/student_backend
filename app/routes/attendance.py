"""Attendance routes: read-only student endpoints and admin-only management endpoints."""

import re
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import (
    get_current_student_profile,
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
    recent_months,
    resolve_student,
    validate_date_str,
    validate_month_str,
)

router = APIRouter(tags=["Attendance"])


# ==========================================
# Student Read-Only Endpoints
# ==========================================


@router.get("/api/student/attendance")
async def get_my_attendance(
    month: Optional[str] = Query(default=None, description="Month (1-12 or YYYY-MM)"),
    year: Optional[str] = Query(default=None, description="Year (YYYY)"),
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return the authenticated student's own attendance records with optional month/year filter."""
    query: Dict[str, Any] = {"student_id": student["_id"]}

    if month and re.fullmatch(r"\d{4}-\d{2}", month.strip()):
        valid_month = validate_month_str(month.strip())
        query["date"] = {"$regex": f"^{valid_month}-"}
    elif year or month:
        if year and not re.fullmatch(r"\d{4}", year.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid year format. Expected YYYY.",
            )
        if month and not re.fullmatch(r"(0?[1-9]|1[0-2])", month.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month value. Expected 1-12 or YYYY-MM.",
            )

        if year and month:
            prefix = f"{year.strip()}-{int(month.strip()):02d}-"
            query["date"] = {"$regex": f"^{prefix}"}
        elif year:
            query["date"] = {"$regex": f"^{year.strip()}-"}
        elif month:
            mm = f"{int(month.strip()):02d}"
            query["date"] = {"$regex": f"^\\d{{4}}-{mm}-"}

    docs = (
        await attendance_collection()
        .find(query)
        .sort("date", -1)
        .to_list(length=1000)
    )
    records = [serialize_attendance(doc, student) for doc in docs]
    summary = calculate_attendance_summary(docs)

    return {
        "student": serialize_student(student),
        "records": records,
        "summary": summary,
    }


@router.get("/api/student/attendance/summary")
async def get_my_attendance_summary(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return attendance summary, current month stats, recent records, and 6-month trend."""
    cur_month = current_month_str()
    months_window = recent_months(6)

    all_docs = (
        await attendance_collection()
        .find({"student_id": student["_id"]})
        .sort("date", -1)
        .to_list(length=1000)
    )
    cur_month_docs = [doc for doc in all_docs if doc["date"].startswith(f"{cur_month}-")]

    overall_summary = calculate_attendance_summary(all_docs)
    current_month_summary = calculate_attendance_summary(cur_month_docs)

    monthly_map: Dict[str, Dict[str, int]] = {
        m: {"present": 0, "absent": 0} for m in months_window
    }
    for rec in all_docs:
        m_key = rec["date"][:7]
        if m_key in monthly_map:
            if rec["status"] == "present":
                monthly_map[m_key]["present"] += 1
            else:
                monthly_map[m_key]["absent"] += 1

    monthly_trend = []
    for m in months_window:
        p = monthly_map[m]["present"]
        a = monthly_map[m]["absent"]
        total = p + a
        monthly_trend.append(
            {
                "month": m,
                "present": p,
                "absent": a,
                "percentage": round((p / total) * 100, 1) if total > 0 else 0,
            }
        )

    return {
        "student": serialize_student(student),
        "current_month": cur_month,
        "overall": overall_summary,
        "current_month_summary": current_month_summary,
        "recent_attendance": [serialize_attendance(doc, student) for doc in all_docs[:5]],
        "monthly_trend": monthly_trend,
    }


# ==========================================
# Admin / Staff Endpoints (Protected)
# ==========================================


@router.post("/api/attendance", status_code=status.HTTP_201_CREATED)
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
                detail=f"Student {student['student_id']} belongs to {student['class_type']} class.",
            )
        if student["_id"] in seen_oids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate attendance entry in request for {student['student_id']}.",
            )
        seen_oids.add(student["_id"])
        resolved_items.append((student, entry.status.lower()))

    existing_docs = await attendance_collection().find(
        {"student_id": {"$in": list(seen_oids)}, "date": date_str}
    ).to_list(length=len(seen_oids))
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
    inserted_docs = await attendance_collection().find(
        {"_id": {"$in": insert_res.inserted_ids}}
    ).to_list(length=len(docs_to_insert))

    return {
        "message": f"Attendance marked for {len(inserted_docs)} student(s).",
        "records": [
            serialize_attendance(rec, student_map.get(rec["student_id"]))
            for rec in inserted_docs
        ],
    }


@router.get("/api/attendance/date/{date}")
async def get_attendance_by_date(
    date: str,
    class_type: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Get all attendance records for a specific date (Admin only)."""
    valid_date = validate_date_str(date)
    query: Dict[str, Any] = {"date": valid_date}
    if class_type and class_type.lower() in {"karate", "skating"}:
        query["class_type"] = class_type.lower()

    docs = await attendance_collection().find(query).to_list(length=1000)
    student_oids = list({doc["student_id"] for doc in docs})
    student_map: Dict[ObjectId, Dict[str, Any]] = {}
    if student_oids:
        async for s_doc in students_collection().find({"_id": {"$in": student_oids}}):
            student_map[s_doc["_id"]] = s_doc

    return {
        "date": valid_date,
        "records": [serialize_attendance(doc, student_map.get(doc["student_id"])) for doc in docs],
        "summary": calculate_attendance_summary(docs),
    }


@router.put("/api/attendance/{attendance_id}")
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
