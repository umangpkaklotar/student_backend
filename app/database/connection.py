"""MongoDB connection manager and index initialization."""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.core.config import get_settings


class DatabaseManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_manager = DatabaseManager()


async def connect_to_mongo() -> None:
    """Connect to MongoDB and ensure required indexes exist."""
    settings = get_settings()
    db_manager.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_manager.db = db_manager.client[settings.DATABASE_NAME]
    await db_manager.client.admin.command("ping")
    await ensure_indexes(db_manager.db)


async def close_mongo_connection() -> None:
    """Close MongoDB client connection."""
    if db_manager.client is not None:
        db_manager.client.close()
        db_manager.client = None
        db_manager.db = None


def get_database() -> AsyncIOMotorDatabase:
    """Return active database instance."""
    if db_manager.db is None:
        raise RuntimeError("Database connection is not initialized.")
    return db_manager.db


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create required unique, query, and TTL indexes on collections."""
    await db["users"].create_index([("email", ASCENDING)], unique=True)
    await db["students"].create_index([("student_id", ASCENDING)], unique=True)
    await db["students"].create_index([("email", ASCENDING)], unique=True)
    await db["students"].create_index([("user_id", ASCENDING)], unique=True)
    await db["otp_verifications"].create_index([("email", ASCENDING)])
    await db["otp_verifications"].create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )
    await db["attendance"].create_index(
        [("student_id", ASCENDING), ("date", ASCENDING)],
        unique=True,
    )
    await db["fees"].create_index(
        [("student_id", ASCENDING), ("month", ASCENDING)],
        unique=True,
    )
