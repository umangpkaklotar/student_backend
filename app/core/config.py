"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from .env file and environment."""

    MONGODB_URL: str = Field(..., description="MongoDB connection URI")
    DATABASE_NAME: str = Field(
        default="student_attendance_db",
        validation_alias=AliasChoices("DATABASE_NAME", "MONGODB_DB_NAME"),
    )
    JWT_SECRET_KEY: str = Field(..., min_length=16, description="JWT signing secret")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    FRONTEND_URL: str = Field(default="http://localhost:5173")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> List[str]:
        origins = [origin.strip() for origin in self.FRONTEND_URL.split(",") if origin.strip()]
        if "http://localhost:5173" not in origins:
            origins.append("http://localhost:5173")
        return origins


@lru_cache()
def get_settings() -> Settings:
    return Settings()
