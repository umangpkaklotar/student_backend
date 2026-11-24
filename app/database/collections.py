"""Collection accessors for MongoDB."""

from motor.motor_asyncio import AsyncIOMotorCollection
from app.database.connection import get_database


def users_collection() -> AsyncIOMotorCollection:
    return get_database()["users"]


def students_collection() -> AsyncIOMotorCollection:
    return get_database()["students"]


def attendance_collection() -> AsyncIOMotorCollection:
    return get_database()["attendance"]


def fees_collection() -> AsyncIOMotorCollection:
    return get_database()["fees"]
