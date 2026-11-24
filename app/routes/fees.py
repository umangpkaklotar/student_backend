"""Fee routes: read-only student endpoints and admin-only management endpoints."""

from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import (
    get_current_student_profile,
    parse_object_id,
    require_admin,
)
from app.database.collections import fees_collection, students_collection
from app.models.fee import build_fee_document, serialize_fee
from app.models.student import serialize_student
from app.schemas.fee import FeeCreate, FeeUpdate
from app.utils.helpers import (
    build_virtual_pending_fee,
    current_month_str,
    resolve_student,
    today_date_str,
    validate_date_str,
    validate_month_str,
)

router = APIRouter(tags=["Fees"])


# ==========================================
# Student Read-Only Endpoints
# ==========================================


@router.get("/api/student/fees")
async def get_my_fees(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return the authenticated student's fee history and current month status."""
    cur_month = current_month_str()
    db_fees = (
        await fees_collection()
        .find({"student_id": student["_id"]})
        .sort("month", -1)
        .to_list(length=200)
    )
    fees_list = [serialize_fee(fee, student) for fee in db_fees]

    current_month_fee = next((f for f in fees_list if f["month"] == cur_month), None)
    if current_month_fee is None and student.get("status") == "active":
        current_month_fee = build_virtual_pending_fee(student, cur_month)
        fees_list.insert(0, current_month_fee)

    paid_total = sum(f["amount"] for f in fees_list if f["status"] == "paid")
    pending_total = sum(f["amount"] for f in fees_list if f["status"] != "paid")

    return {
        "student": serialize_student(student),
        "current_month": cur_month,
        "current_month_fee": current_month_fee,
        "fees": fees_list,
        "summary": {
            "total_paid": paid_total,
            "total_pending": pending_total,
            "paid_months": sum(1 for f in fees_list if f["status"] == "paid"),
            "pending_months": sum(1 for f in fees_list if f["status"] != "paid"),
        },
    }


@router.get("/api/student/fees/current")
async def get_my_current_month_fee(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return the authenticated student's current month fee status."""
    cur_month = current_month_str()
    fee_doc = await fees_collection().find_one(
        {"student_id": student["_id"], "month": cur_month}
    )
    if fee_doc:
        current_fee = serialize_fee(fee_doc, student)
    else:
        current_fee = build_virtual_pending_fee(student, cur_month)

    return {
        "student": serialize_student(student),
        "month": cur_month,
        "fee": current_fee,
    }


# ==========================================
# Admin / Staff Endpoints (Protected)
# ==========================================


@router.post("/api/fees", status_code=status.HTTP_201_CREATED)
async def create_fee_record(
    payload: FeeCreate,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Create a monthly fee record for a student (Admin only)."""
    student = await resolve_student(payload.student_id)
    valid_month = validate_month_str(payload.month)

    existing = await fees_collection().find_one(
        {"student_id": student["_id"], "month": valid_month}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate monthly fee: record already exists for {student['student_id']} in {valid_month}.",
        )

    amount = float(payload.amount) if payload.amount is not None else float(student["monthly_fee"])
    status_val = payload.status.lower()
    payment_date = (
        validate_date_str(payload.payment_date)
        if payload.payment_date
        else (today_date_str() if status_val == "paid" else None)
    )

    fee_doc = build_fee_document(
        student_oid=student["_id"],
        month=valid_month,
        amount=amount,
        status_val=status_val,
        payment_date=payment_date,
        payment_method=payload.payment_method,
        notes=payload.notes,
    )

    try:
        result = await fees_collection().insert_one(fee_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate monthly fee for {student['student_id']} in {valid_month}.",
        ) from exc

    created = await fees_collection().find_one({"_id": result.inserted_id})
    return {
        "message": "Monthly fee record created successfully.",
        "fee": serialize_fee(created, student),
    }


def _fee_matches_filters(
    fee_item: Dict[str, Any],
    status_filter: Optional[str],
    class_filter: Optional[str],
    search: Optional[str],
) -> bool:
    if status_filter and fee_item.get("status") != status_filter.lower():
        return False
    if class_filter and fee_item.get("class_type") != class_filter.lower():
        return False
    if search and search.strip():
        needle = search.strip().lower()
        haystack = f"{fee_item.get('student_code', '')} {fee_item.get('student_name', '')}".lower()
        if needle not in haystack:
            return False
    return True


@router.get("/api/fees")
async def list_fees(
    month: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    class_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """List fee records including virtual pending current-month fees for active students (Admin only)."""
    target_month = validate_month_str(month) if month else None
    virtual_month = target_month or current_month_str()

    query: Dict[str, Any] = {}
    if target_month:
        query["month"] = target_month

    db_fees = await fees_collection().find(query).sort("month", -1).to_list(length=2000)
    students = await students_collection().find({}).to_list(length=2000)
    student_map: Dict[ObjectId, Dict[str, Any]] = {s["_id"]: s for s in students}

    recorded_for_virtual_month: set[ObjectId] = set()
    items: List[Dict[str, Any]] = []

    for fee in db_fees:
        student = student_map.get(fee["student_id"])
        if not student:
            continue
        if fee["month"] == virtual_month:
            recorded_for_virtual_month.add(fee["student_id"])
        serialized = serialize_fee(fee, student)
        if _fee_matches_filters(serialized, status_filter, class_type, search):
            items.append(serialized)

    for student in students:
        if student.get("status") != "active":
            continue
        if student["_id"] in recorded_for_virtual_month:
            continue
        virtual_item = build_virtual_pending_fee(student, virtual_month)
        if _fee_matches_filters(virtual_item, status_filter, class_type, search):
            items.append(virtual_item)

    total_amount = sum(item["amount"] for item in items)
    paid_amount = sum(item["amount"] for item in items if item["status"] == "paid")
    pending_amount = sum(item["amount"] for item in items if item["status"] != "paid")

    return {
        "fees": items,
        "month": virtual_month,
        "summary": {
            "total_records": len(items),
            "paid_count": sum(1 for item in items if item["status"] == "paid"),
            "pending_count": sum(1 for item in items if item["status"] == "pending"),
            "partial_count": sum(1 for item in items if item["status"] == "partial"),
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "pending_amount": pending_amount,
        },
    }


@router.put("/api/fees/{fee_id}")
async def update_fee(
    fee_id: str,
    payload: FeeUpdate,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Update a monthly fee record (Admin only)."""
    fee_oid = parse_object_id(fee_id, "fee_id")
    existing = await fees_collection().find_one({"_id": fee_oid})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fee record not found.",
        )

    updates: Dict[str, Any] = {}
    if payload.amount is not None:
        updates["amount"] = float(payload.amount)
    if payload.status is not None:
        updates["status"] = payload.status.lower()
    if payload.payment_method is not None:
        updates["payment_method"] = payload.payment_method
    if payload.notes is not None:
        updates["notes"] = payload.notes

    if payload.payment_date is not None:
        updates["payment_date"] = validate_date_str(payload.payment_date)
    elif updates.get("status") == "paid" and not existing.get("payment_date"):
        updates["payment_date"] = today_date_str()
    elif updates.get("status") == "pending":
        updates["payment_date"] = None

    if updates:
        await fees_collection().update_one({"_id": fee_oid}, {"$set": updates})

    updated = await fees_collection().find_one({"_id": fee_oid})
    student = await students_collection().find_one({"_id": updated["student_id"]})

    return {
        "message": "Fee record updated successfully.",
        "fee": serialize_fee(updated, student),
    }
