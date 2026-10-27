import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to backend/.env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "AETHER Life API"
    VERSION: str = "0.3.0"
    API_PREFIX: str = "/api"
    DATABASE_URL: str = "sqlite:///./aether_life.db"

    # Scheduler Settings
    CHECKIN_SCHEDULER_ENABLED: bool = True
    CHECKIN_SCHEDULE_CRON: str = "0 9 * * *"
    CHECKIN_EXPIRATION_CHECK_INTERVAL_SECONDS: int = 60
    CHECKIN_DEFAULT_TIMEOUT_MINUTES: int = 60
    SCHEDULER_TIMEZONE: str = "Asia/Tokyo"

    # Gemini & AI Safety Settings (Cost & Billing Protection)
    # Default is False to completely prevent unintended cloud billing
    GEMINI_API_ENABLED: bool = False
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL_ID: str = "gemini-3.8-flash"
    GEMINI_MAX_DAILY_CALLS: int = 50
    GEMINI_AUTO_RETRY: bool = False
    MOCK_CAMERA_DIR: str = "tests/fixtures/mock_images"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

settings = Settings()
