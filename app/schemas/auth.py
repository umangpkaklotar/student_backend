"""Pydantic schemas for authentication, registration, and password reset."""

import re
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


def normalize_indian_mobile(value: str) -> str:
    """Validate and normalize a 10-digit Indian mobile number."""
    cleaned = re.sub(r"[\s\-()]+", "", value.strip())
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    if not re.fullmatch(r"[6-9]\d{9}", cleaned):
        raise ValueError("Enter a valid 10-digit Indian mobile number starting with 6-9.")
    return cleaned


class RegisterSendOtpRequest(BaseModel):
    email: EmailStr
    resend: bool = False
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    confirm_password: Optional[str] = None
    gender: Optional[Literal["Male", "Female", "Other"]] = None
    date_of_birth: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    address: Optional[str] = Field(default=None, min_length=3, max_length=300)
    class_type: Optional[Literal["karate", "skating"]] = None

    @field_validator("class_type", mode="before")
    @classmethod
    def normalize_class(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_indian_mobile(v)

    @model_validator(mode="after")
    def validate_registration_fields(self) -> "RegisterSendOtpRequest":
        if not self.resend:
            required = {
                "name": self.name,
                "phone": self.phone,
                "password": self.password,
                "confirm_password": self.confirm_password,
                "gender": self.gender,
                "date_of_birth": self.date_of_birth,
                "address": self.address,
                "class_type": self.class_type,
            }
            missing = [k for k, v in required.items() if not v]
            if missing:
                raise ValueError(f"Missing required field(s): {', '.join(missing)}")
            if self.password != self.confirm_password:
                raise ValueError("Password and confirm password do not match.")
        return self


class RegisterVerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., pattern=r"^\d{6}$", description="6-digit numeric OTP")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["admin", "student"]
    email_verified: bool = True
    status: str = "active"
    created_at: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "student"]
    user: UserResponse


class ForgotPasswordSendOtpRequest(BaseModel):
    email: EmailStr


class ForgotPasswordVerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., pattern=r"^\d{6}$")


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirm password do not match.")
        return self


class AdminProfileUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(default=None, min_length=6)
