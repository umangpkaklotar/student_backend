"""Shared helper functions for ID generation, dates, and calculations."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from bson import ObjectId
from fastapi import HTTPException, status

from app.database.collections import students_collection

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Return current datetime in Indian Standard Time (UTC+05:30)."""
    return datetime.now(IST)


def current_month_str() -> str:
    """Return current month in IST formatted as YYYY-MM."""
    return now_ist().strftime("%Y-%m")


def today_date_str() -> str:
    """Return today's date in IST formatted as YYYY-MM-DD."""
    return now_ist().strftime("%Y-%m-%d")


def validate_date_str(date_str: str) -> str:
    """Validate YYYY-MM-DD date string."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Expected YYYY-MM-DD.",
        )
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid calendar date.",
        ) from exc
    return date_str


def validate_month_str(month_str: str) -> str:
    """Validate YYYY-MM month string."""
    if not re.fullmatch(r"\d{4}-\d{2}", month_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid month format. Expected YYYY-MM.",
        )
    try:
        datetime.strptime(month_str, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid month value.",
        ) from exc
    return month_str


def recent_months(count: int = 6) -> List[str]:
    """Return the last `count` months in chronological order as YYYY-MM."""
    now = now_ist()
    year = now.year
    month = now.month
    months: List[str] = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


async def generate_next_student_id() -> str:
    """Generate the next unique student code (e.g. STU-001, STU-002)."""
    cursor = students_collection().find({}, {"student_id": 1})
    max_num = 0
    async for doc in cursor:
        code = doc.get("student_id", "")
        match = re.fullmatch(r"STU-(\d+)", str(code))
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return f"STU-{max_num + 1:03d}"


async def resolve_student(student_identifier: str) -> Dict[str, Any]:
    """Find a student by MongoDB ObjectId or STU-XXX code."""
    if ObjectId.is_valid(student_identifier):
        student = await students_collection().find_one({"_id": ObjectId(student_identifier)})
    elif re.fullmatch(r"STU-\d+", student_identifier, re.IGNORECASE):
        student = await students_collection().find_one(
            {"student_id": student_identifier.upper()}
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ObjectId: {student_identifier}",
        )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found.",
        )
    return student


def calculate_attendance_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate total classes, present, absent, and attendance percentage."""
    total_classes = len(records)
    present = sum(1 for r in records if r.get("status") == "present")
    absent = total_classes - present
    attendance_percentage = (
        round((present / total_classes) * 100, 2) if total_classes > 0 else 0.0
    )
    return {
        "total_classes": total_classes,
        "present": present,
        "absent": absent,
        "attendance_percentage": attendance_percentage,
    }


def build_virtual_pending_fee(student: Dict[str, Any], month: str) -> Dict[str, Any]:
    """Construct an unsaved pending fee view for an active student."""
    return {
        "id": None,
        "student_id": str(student["_id"]),
        "student_code": student["student_id"],
        "student_name": student["name"],
        "class_type": student["class_type"],
        "month": month,
        "amount": float(student["monthly_fee"]),
        "status": "pending",
        "payment_date": None,
        "payment_method": None,
        "notes": None,
        "created_at": None,
        "is_virtual": True,
    }
