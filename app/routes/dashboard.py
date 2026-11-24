"""Dashboard and reporting routes for Admin and Student roles."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_student_profile, require_admin
from app.database.collections import (
    attendance_collection,
    fees_collection,
    students_collection,
)
from app.models.attendance import serialize_attendance
from app.models.fee import serialize_fee
from app.models.student import serialize_student
from app.utils.helpers import (
    build_virtual_pending_fee,
    calculate_attendance_summary,
    current_month_str,
    recent_months,
    resolve_student,
    today_date_str,
    validate_date_str,
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/admin")
async def get_admin_dashboard(
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Return summary cards and chart analytics for the Admin dashboard."""
    today = today_date_str()
    cur_month = current_month_str()
    months_window = recent_months(6)

    students = await students_collection().find({}).to_list(length=5000)
    active_students = [s for s in students if s.get("status") == "active"]

    karate_students = sum(1 for s in active_students if s.get("class_type") == "karate")
    skating_students = sum(1 for s in active_students if s.get("class_type") == "skating")

    today_attendance = await attendance_collection().find({"date": today}).to_list(length=5000)
    present_today = sum(1 for a in today_attendance if a.get("status") == "present")
    absent_today = sum(1 for a in today_attendance if a.get("status") == "absent")

    # Current month fees (combine real records + virtual pending for active students)
    cur_month_fees = await fees_collection().find({"month": cur_month}).to_list(length=5000)
    cur_fee_by_student = {f["student_id"]: f for f in cur_month_fees}

    paid_fees_count = 0
    paid_fees_amount = 0.0
    pending_fees_count = 0
    pending_fees_amount = 0.0

    for student in active_students:
        fee_doc = cur_fee_by_student.get(student["_id"])
        if fee_doc:
            if fee_doc["status"] == "paid":
                paid_fees_count += 1
                paid_fees_amount += float(fee_doc["amount"])
            else:
                pending_fees_count += 1
                pending_fees_amount += float(fee_doc["amount"])
        else:
            pending_fees_count += 1
            pending_fees_amount += float(student["monthly_fee"])

    # Monthly attendance chart (last 6 months)
    all_window_att = await attendance_collection().find(
        {"date": {"$gte": f"{months_window[0]}-01"}}
    ).to_list(length=20000)
    monthly_att_map: Dict[str, Dict[str, int]] = {
        m: {"present": 0, "absent": 0} for m in months_window
    }
    for rec in all_window_att:
        m_key = rec["date"][:7]
        if m_key in monthly_att_map:
            if rec["status"] == "present":
                monthly_att_map[m_key]["present"] += 1
            else:
                monthly_att_map[m_key]["absent"] += 1

    monthly_attendance = []
    for m in months_window:
        p = monthly_att_map[m]["present"]
        a = monthly_att_map[m]["absent"]
        total = p + a
        monthly_attendance.append(
            {
                "month": m,
                "present": p,
                "absent": a,
                "percentage": round((p / total) * 100, 1) if total > 0 else 0,
            }
        )

    # Monthly fee collection chart (last 6 months)
    all_window_fees = await fees_collection().find(
        {"month": {"$in": months_window}}
    ).to_list(length=20000)
    monthly_fee_map: Dict[str, Dict[str, float]] = {
        m: {"paid": 0.0, "pending": 0.0} for m in months_window
    }
    recorded_per_month: Dict[str, set] = {m: set() for m in months_window}
    for fee in all_window_fees:
        m_key = fee["month"]
        if m_key in monthly_fee_map:
            recorded_per_month[m_key].add(fee["student_id"])
            if fee["status"] == "paid":
                monthly_fee_map[m_key]["paid"] += float(fee["amount"])
            else:
                monthly_fee_map[m_key]["pending"] += float(fee["amount"])

    # Include virtual pending for current month in chart
    for student in active_students:
        if student["_id"] not in recorded_per_month[cur_month]:
            monthly_fee_map[cur_month]["pending"] += float(student["monthly_fee"])

    monthly_fee_collection = [
        {
            "month": m,
            "paid": round(monthly_fee_map[m]["paid"], 2),
            "pending": round(monthly_fee_map[m]["pending"], 2),
        }
        for m in months_window
    ]

    return {
        "cards": {
            "total_students": len(students),
            "active_students": len(active_students),
            "karate_students": karate_students,
            "skating_students": skating_students,
            "present_today": present_today,
            "absent_today": absent_today,
            "pending_fees_count": pending_fees_count,
            "pending_fees_amount": round(pending_fees_amount, 2),
            "paid_fees_count": paid_fees_count,
            "paid_fees_amount": round(paid_fees_amount, 2),
        },
        "charts": {
            "monthly_attendance": monthly_attendance,
            "class_distribution": [
                {"name": "Karate", "value": karate_students},
                {"name": "Skating", "value": skating_students},
            ],
            "monthly_fee_collection": monthly_fee_collection,
            "fee_status_breakdown": [
                {"name": "Paid", "value": round(paid_fees_amount, 2), "count": paid_fees_count},
                {"name": "Pending", "value": round(pending_fees_amount, 2), "count": pending_fees_count},
            ],
        },
        "current_month": cur_month,
        "today": today,
    }


@router.get("/reports")
async def get_admin_reports(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    class_type: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Generate filtered attendance and fee reports for Admin."""
    student_query: Dict[str, Any] = {}
    if class_type and class_type.lower() in {"karate", "skating"}:
        student_query["class_type"] = class_type.lower()

    if student_id:
        target_student = await resolve_student(student_id)
        student_query["_id"] = target_student["_id"]

    students = await students_collection().find(student_query).sort("student_id", 1).to_list(length=5000)
    student_oids = [s["_id"] for s in students]

    att_query: Dict[str, Any] = {"student_id": {"$in": student_oids}}
    if start_date or end_date:
        date_filter: Dict[str, str] = {}
        if start_date:
            date_filter["$gte"] = validate_date_str(start_date)
        if end_date:
            date_filter["$lte"] = validate_date_str(end_date)
        att_query["date"] = date_filter

    att_records = (
        await attendance_collection().find(att_query).to_list(length=50000)
        if student_oids
        else []
    )

    fee_query: Dict[str, Any] = {"student_id": {"$in": student_oids}}
    if start_date or end_date:
        month_filter: Dict[str, str] = {}
        if start_date:
            month_filter["$gte"] = validate_date_str(start_date)[:7]
        if end_date:
            month_filter["$lte"] = validate_date_str(end_date)[:7]
        fee_query["month"] = month_filter

    fee_records = (
        await fees_collection().find(fee_query).to_list(length=20000)
        if student_oids
        else []
    )

    cur_month = current_month_str()
    include_cur_month_virtual = True
    if start_date and start_date[:7] > cur_month:
        include_cur_month_virtual = False
    if end_date and end_date[:7] < cur_month:
        include_cur_month_virtual = False

    att_by_student: Dict[Any, List[Dict[str, Any]]] = {s["_id"]: [] for s in students}
    for rec in att_records:
        if rec["student_id"] in att_by_student:
            att_by_student[rec["student_id"]].append(rec)

    fee_by_student: Dict[Any, List[Dict[str, Any]]] = {s["_id"]: [] for s in students}
    for fee in fee_records:
        if fee["student_id"] in fee_by_student:
            fee_by_student[fee["student_id"]].append(fee)

    rows = []
    total_present = 0
    total_absent = 0
    total_paid_fees = 0.0
    total_pending_fees = 0.0

    for student in students:
        sid = student["_id"]
        s_att = att_by_student[sid]
        att_summary = calculate_attendance_summary(s_att)
        total_present += att_summary["present"]
        total_absent += att_summary["absent"]

        s_fees = fee_by_student[sid]
        has_cur_month = any(f["month"] == cur_month for f in s_fees)
        paid_amt = sum(float(f["amount"]) for f in s_fees if f["status"] == "paid")
        pending_amt = sum(float(f["amount"]) for f in s_fees if f["status"] != "paid")
        if include_cur_month_virtual and student.get("status") == "active" and not has_cur_month:
            pending_amt += float(student["monthly_fee"])

        total_paid_fees += paid_amt
        total_pending_fees += pending_amt

        rows.append(
            {
                "id": str(sid),
                "student_id": student["student_id"],
                "name": student["name"],
                "class_type": student["class_type"],
                "status": student["status"],
                "total_classes": att_summary["total_classes"],
                "present": att_summary["present"],
                "absent": att_summary["absent"],
                "attendance_percentage": att_summary["attendance_percentage"],
                "paid_fees": round(paid_amt, 2),
                "pending_fees": round(pending_amt, 2),
                "total_fees": round(paid_amt + pending_amt, 2),
            }
        )

    total_att = total_present + total_absent
    overall_pct = round((total_present / total_att) * 100, 2) if total_att > 0 else 0.0

    return {
        "summary": {
            "total_students": len(students),
            "total_attendance": total_att,
            "present": total_present,
            "absent": total_absent,
            "attendance_percentage": overall_pct,
            "total_fees": round(total_paid_fees + total_pending_fees, 2),
            "paid_fees": round(total_paid_fees, 2),
            "pending_fees": round(total_pending_fees, 2),
        },
        "rows": rows,
    }


@router.get("/student")
async def get_student_dashboard(
    student: Dict[str, Any] = Depends(get_current_student_profile),
) -> Dict[str, Any]:
    """Return personal attendance, fee status, and charts for the authenticated Student."""
    cur_month = current_month_str()
    months_window = recent_months(6)

    all_attendance = (
        await attendance_collection()
        .find({"student_id": student["_id"]})
        .sort("date", -1)
        .to_list(length=1000)
    )
    month_attendance = [
        rec for rec in all_attendance if rec["date"].startswith(f"{cur_month}-")
    ]

    cur_month_summary = calculate_attendance_summary(month_attendance)
    overall_summary = calculate_attendance_summary(all_attendance)

    # Monthly attendance chart for last 6 months
    monthly_map: Dict[str, Dict[str, int]] = {
        m: {"present": 0, "absent": 0} for m in months_window
    }
    for rec in all_attendance:
        m_key = rec["date"][:7]
        if m_key in monthly_map:
            if rec["status"] == "present":
                monthly_map[m_key]["present"] += 1
            else:
                monthly_map[m_key]["absent"] += 1

    monthly_chart = []
    for m in months_window:
        p = monthly_map[m]["present"]
        a = monthly_map[m]["absent"]
        total = p + a
        monthly_chart.append(
            {
                "month": m,
                "present": p,
                "absent": a,
                "percentage": round((p / total) * 100, 1) if total > 0 else 0,
            }
        )

    all_fees = (
        await fees_collection()
        .find({"student_id": student["_id"]})
        .sort("month", -1)
        .to_list(length=200)
    )
    serialized_fees = [serialize_fee(f, student) for f in all_fees]
    current_month_fee = next((f for f in serialized_fees if f["month"] == cur_month), None)
    if current_month_fee is None and student.get("status") == "active":
        current_month_fee = build_virtual_pending_fee(student, cur_month)
        serialized_fees.insert(0, current_month_fee)

    return {
        "student": serialize_student(student),
        "current_month": cur_month,
        "current_month_attendance": {
            "month": cur_month,
            **cur_month_summary,
        },
        "overall_attendance": overall_summary,
        "current_month_fee": current_month_fee,
        "recent_attendance": [serialize_attendance(r, student) for r in all_attendance[:10]],
        "recent_payments": serialized_fees[:10],
        "monthly_attendance_chart": monthly_chart,
    }
