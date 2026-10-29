"""Centralized settings for MedBalance services."""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Infrastructure
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "medbal-service"
    DATABASE_URL: str = "postgresql+psycopg://medbal:medbal@localhost:5432/medbal"
    REDIS_URL: str = "redis://localhost:6379/0"
    MQTT_URL: str = "mqtt://localhost:1883"

    # Execution & Simulation
    DEMO_MODE: Literal["live", "record", "replay"] = "live"
    USE_FIXTURES: bool = False
    SIM_START_DATE: str = "2026-11-01T08:00:00+05:30"

    # Service URLs
    SIM_CONTROL_URL: str = "http://localhost:8100"
    CORE_API_URL: str = "http://localhost:8001"
    INGEST_AI_URL: str = "http://localhost:8002"
    GENAI_URL: str = "http://localhost:8003"
    FORECAST_URL: str = "http://localhost:8004"
    OPTIMIZER_URL: str = "http://localhost:8005"
    COLDCHAIN_URL: str = "http://localhost:8006"
    SIM_HOSPITAL_H1_URL: str = "http://localhost:8101"
    SIM_HOSPITAL_H2_URL: str = "http://localhost:8102"
    SIM_HOSPITAL_H3_URL: str = "http://localhost:8103"
    SIM_HOSPITAL_H4_URL: str = "http://localhost:8104"

    # LLM Settings (CLAUDE.md §8)
    LLM_MODEL_FAST: str = "claude-3-5-haiku-20241022"
    LLM_MODEL_SMART: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    # QpiAI Settings (CLAUDE.md §7)
    QPIAI_API_KEY: str | None = None
    QPIAI_ENDPOINT: str = "https://api.qpiai.tech"


@lru_cache
def get_settings() -> Settings:
    return Settings()
