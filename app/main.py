"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.database.connection import close_mongo_connection, connect_to_mongo
from app.routes import attendance, auth, dashboard, enrollment, fees, profile, students


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


settings = get_settings()

app = FastAPI(
    title="Student Attendance & Fee Management System API",
    description=(
        "Production REST API for Student Registration with Gmail OTP Verification, "
        "JWT Authentication, Attendance Viewing, Fee Status Viewing, and Profile Management."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)+(workers\.dev|pages\.dev)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.detail,
            "message": exc.detail if isinstance(exc.detail, str) else "Request error",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    first_msg = errors[0].get("msg", "Validation error") if errors else "Validation error"
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "detail": first_msg,
            "message": first_msg,
            "errors": errors,
        },
    )


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(enrollment.router)
app.include_router(students.router)
app.include_router(attendance.router)
app.include_router(fees.router)
app.include_router(dashboard.router)


@app.get("/", tags=["Health"])
async def root() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "Student Attendance & Fee Management System API",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
