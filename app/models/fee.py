"""MongoDB document helpers for the fees collection."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from bson import ObjectId


def serialize_fee(
    fee: Dict[str, Any],
    student: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert a MongoDB fee document into an API-safe dictionary."""
    result = {
        "id": str(fee["_id"]),
        "student_id": str(fee["student_id"]),
        "month": fee["month"],
        "amount": float(fee["amount"]),
        "status": fee["status"],
        "payment_date": fee.get("payment_date"),
        "payment_method": fee.get("payment_method"),
        "notes": fee.get("notes"),
        "created_at": fee["created_at"].isoformat()
        if isinstance(fee.get("created_at"), datetime)
        else fee.get("created_at"),
        "is_virtual": bool(fee.get("is_virtual", False)),
    }
    if student is not None:
        result["student_code"] = student.get("student_id")
        result["student_name"] = student.get("name")
        result["class_type"] = student.get("class_type")
    return result


def build_fee_document(
    student_oid: ObjectId,
    month: str,
    amount: float,
    status_val: str,
    payment_date: Optional[str] = None,
    payment_method: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a fee document for insertion into MongoDB."""
    return {
        "student_id": student_oid,
        "month": month,
        "amount": float(amount),
        "status": status_val.lower(),
        "payment_date": payment_date,
        "payment_method": payment_method,
        "notes": notes,
        "created_at": datetime.now(timezone.utc),
    }
