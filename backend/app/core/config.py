import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "AETHER Life API"
    VERSION: str = "0.3.0"
    API_PREFIX: str = "/api"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./aether_life.db")

    model_config = SettingsConfigDict(case_sensitive=True)

settings = Settings()
