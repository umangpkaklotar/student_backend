"""Pydantic schemas for class enrollment."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import normalize_indian_mobile


class EnrollmentCreateOrUpdate(BaseModel):
    class_type: Literal["karate", "skating"]
    emergency_contact_name: str = Field(..., min_length=2, max_length=100)
    emergency_contact_number: str
    previous_experience: str = Field(default="None", max_length=300)
    preferred_batch: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = None
    address: Optional[str] = Field(default=None, min_length=3, max_length=300)
    date_of_birth: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("class_type", mode="before")
    @classmethod
    def normalize_class(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("emergency_contact_number")
    @classmethod
    def validate_emergency_phone(cls, v: str) -> str:
        return normalize_indian_mobile(v)

    @field_validator("phone")
    @classmethod
    def validate_optional_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_indian_mobile(v) if v is not None else v


class EnrollmentRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)
