from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.checkin import (
    CheckinCreate,
    CheckinRespondRequest,
    CheckinResponse,
)
from app.services.checkin_service import (
    CheckinService,
    CheckinNotFoundError,
    CheckinInvalidStatusError,
)

router = APIRouter(prefix="/checkins", tags=["checkins"])

@router.get("/current", response_model=Optional[CheckinResponse])
def get_current_checkin(db: Session = Depends(get_db)):
    service = CheckinService(db)
    return service.get_current_pending_checkin()

@router.post("/respond", response_model=CheckinResponse)
def respond_checkin(
    payload: CheckinRespondRequest,
    db: Session = Depends(get_db)
):
    service = CheckinService(db)
    try:
        return service.respond_to_checkin(
            checkin_id=payload.checkin_id,
            response_message=payload.response_message
        )
    except CheckinNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except CheckinInvalidStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("", response_model=CheckinResponse, status_code=status.HTTP_201_CREATED)
def create_checkin(
    checkin_in: CheckinCreate,
    db: Session = Depends(get_db)
):
    service = CheckinService(db)
    return service.create_checkin(checkin_in)
