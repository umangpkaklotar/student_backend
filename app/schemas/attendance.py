"""Pydantic schemas for attendance management."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class AttendanceEntry(BaseModel):
    student_id: str = Field(..., description="Student MongoDB ObjectId or STU-XXX code")
    status: Literal["present", "absent"]

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class AttendanceCreate(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    class_type: Literal["karate", "skating"]
    records: Optional[List[AttendanceEntry]] = None
    student_id: Optional[str] = None
    status: Optional[Literal["present", "absent"]] = None

    @field_validator("class_type", mode="before")
    @classmethod
    def normalize_class_type(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v


class AttendanceUpdate(BaseModel):
    status: Literal["present", "absent"]

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v
