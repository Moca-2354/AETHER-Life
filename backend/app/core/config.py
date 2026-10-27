import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "AETHER Life API"
    VERSION: str = "0.3.0"
    API_PREFIX: str = "/api"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./aether_life.db")

    # Scheduler Settings
    CHECKIN_SCHEDULER_ENABLED: bool = os.getenv("CHECKIN_SCHEDULER_ENABLED", "True").lower() in ("true", "1", "t")
    CHECKIN_SCHEDULE_CRON: str = os.getenv("CHECKIN_SCHEDULE_CRON", "0 9 * * *")
    CHECKIN_EXPIRATION_CHECK_INTERVAL_SECONDS: int = int(os.getenv("CHECKIN_EXPIRATION_CHECK_INTERVAL_SECONDS", "60"))
    CHECKIN_DEFAULT_TIMEOUT_MINUTES: int = int(os.getenv("CHECKIN_DEFAULT_TIMEOUT_MINUTES", "60"))
    SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Tokyo")

    model_config = SettingsConfigDict(case_sensitive=True)

settings = Settings()
