"""Pydantic schemas for monthly fee management."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class FeeCreate(BaseModel):
    student_id: str = Field(..., description="Student MongoDB ObjectId or STU-XXX code")
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    amount: Optional[float] = Field(default=None, gt=0)
    status: Literal["paid", "pending", "partial"] = "pending"
    payment_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    payment_method: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class FeeUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    status: Optional[Literal["paid", "pending", "partial"]] = None
    payment_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    payment_method: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v
