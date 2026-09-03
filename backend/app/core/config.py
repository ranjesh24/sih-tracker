"""Application configuration.

Every tunable value in ``techspec.md`` §7 (backend ``.env`` block), loaded from
the environment via ``pydantic-settings``. No magic numbers live in logic
(``rules.md`` §3): thresholds, weights, windows and speed bounds all live here.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings. Field names match ``techspec.md`` §7 exactly."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- core ---
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite:///./data/marg.db"

    # --- auth / security ---
    # Secrets default to empty here; startup validation (session 2) must reject an
    # empty value. rules.md §8: no real secret in the repo, ever.
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    INGEST_API_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- resolution / vector index ---
    EMBEDDING_DIM: int = 512
    VISUAL_FLOOR: float = 0.55
    AMBIGUITY_MARGIN: float = 0.05
    FAISS_TOP_K: int = 50
    LOOKBACK_WINDOW_SECONDS: int = 3600

    # --- fusion weights (amended 2026-09-02, TASK-000) ---
    W_VISUAL: float = 0.45
    W_PLATE: float = 0.20
    W_TEMPORAL: float = 0.55

    # --- spatio-temporal gate ---
    ROAD_WINDING_FACTOR: float = 1.35
    MAX_PLAUSIBLE_SPEED_KMH: float = 80.0
    MIN_PLAUSIBLE_SPEED_KMH: float = 8.0
    MIN_REVISIT_SECONDS: int = 30

    # --- storage / ops ---
    CROP_STORAGE_PATH: str = "./data/crops"
    RETENTION_DAYS: int = 30
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
