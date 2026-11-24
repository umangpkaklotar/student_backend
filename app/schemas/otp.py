"""Pydantic schemas for OTP responses."""

from pydantic import BaseModel, EmailStr


class OtpSendResponse(BaseModel):
    success: bool = True
    message: str
    email: EmailStr
    expires_in_seconds: int
    resend_cooldown_seconds: int


class ForgotPasswordVerifyResponse(BaseModel):
    success: bool = True
    message: str
    reset_token: str
