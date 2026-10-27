from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.session import engine
from app.db.migrate import migrate_db
from app.api.router import api_router
from app.services.scheduler_service import checkin_scheduler
# Ensure all models are registered on Base.metadata
import app.models  # noqa: F401

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize and migrate database schema
    migrate_db(engine)

    # 2. Start Checkin Scheduler (includes startup recovery)
    checkin_scheduler.start()

    yield

    # 3. Graceful shutdown of scheduler
    checkin_scheduler.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Maintain existing /health endpoint
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AETHER Life"
    }

# Include API router with /api prefix
app.include_router(api_router, prefix=settings.API_PREFIX)
