from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.api.router import api_router
# Import all models to ensure they are registered on Base.metadata
import app.models  # noqa: F401

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    Base.metadata.create_all(bind=engine)
    yield

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
