"""Pydantic schemas for authentication."""

from typing import Literal
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["admin", "student"]
    created_at: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "student"]
    user: UserResponse


class AdminProfileUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6)
