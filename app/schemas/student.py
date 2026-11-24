"""Pydantic schemas for student management and student self-profile updates."""

from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import normalize_indian_mobile


class StudentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: str
    gender: Literal["Male", "Female", "Other"]
    date_of_birth: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    address: str = Field(..., min_length=3, max_length=300)
    class_type: Literal["karate", "skating"]
    joining_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    monthly_fee: float = Field(..., gt=0)

    @field_validator("class_type", mode="before")
    @classmethod
    def normalize_class_type(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_indian_mobile(v)


class StudentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    phone: Optional[str] = None
    gender: Optional[Literal["Male", "Female", "Other"]] = None
    date_of_birth: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    address: Optional[str] = Field(default=None, min_length=3, max_length=300)
    class_type: Optional[Literal["karate", "skating"]] = None
    joining_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    monthly_fee: Optional[float] = Field(default=None, gt=0)
    status: Optional[Literal["active", "inactive"]] = None

    @field_validator("class_type", mode="before")
    @classmethod
    def normalize_class_type(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_indian_mobile(v) if v is not None else v


class StudentSelfProfileUpdate(BaseModel):
    """Allowed safe profile fields a student may update."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = None
    gender: Optional[Literal["Male", "Female", "Other"]] = None
    date_of_birth: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    address: Optional[str] = Field(default=None, min_length=3, max_length=300)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_indian_mobile(v) if v is not None else v
