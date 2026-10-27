from fastapi import APIRouter
from app.api.v1.events import router as events_router
from app.api.v1.checkins import router as checkins_router
from app.api.v1.camera import router as camera_router
from app.api.v1.safety import router as safety_router

api_router = APIRouter()
api_router.include_router(events_router)
api_router.include_router(checkins_router)
api_router.include_router(camera_router)
api_router.include_router(safety_router)
