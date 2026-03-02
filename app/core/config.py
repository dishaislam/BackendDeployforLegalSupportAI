import os
from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "LegalSupportAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres123"
    POSTGRES_DB: str = "legalsupportai"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: str = "5432"
    DATABASE_URL: str = ""  # Auto-built below

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self

    # JWT
    JWT_SECRET_KEY: str = "change-this-to-a-secure-random-string-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Firebase
    FIREBASE_SERVICE_ACCOUNT: str = ""

    # Mistral AI
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"

    # Qdrant
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "bdlaws_sections_v1"

    # Retrieval
    TOP_K_VECTOR: int = 12
    TOP_K_FINAL: int = 10
    SCORE_THRESHOLD: float = 0.60
    JURISDICTION_DEFAULT: str = "Bangladesh"

    # Data paths
    DATA_DIR: str = "/app/data"

    @property
    def DOCSTORE_PATH(self) -> str:
        return os.path.join(self.DATA_DIR, "docstore.jsonl")

    @property
    def BM25_PATH(self) -> str:
        return os.path.join(self.DATA_DIR, "bm25.pkl")


settings = Settings()