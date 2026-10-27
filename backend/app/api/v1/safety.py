from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.safety import SafetyAnalyzeRequest, SafetyAnalyzeResponse
from app.services.camera_service import CameraService, CameraError, get_camera_service
from app.services.gemini_service import (
    GeminiServiceInterface,
    GeminiQuotaExceededError,
    GeminiDisabledError,
    get_gemini_service,
)
from app.services.safety_controller import SafetyController, ConsentRequiredError

router = APIRouter(prefix="/safety", tags=["safety"])

def get_safety_controller(
    camera_service: CameraService = Depends(get_camera_service),
    gemini_service: GeminiServiceInterface = Depends(get_gemini_service),
    db: Session = Depends(get_db)
) -> SafetyController:
    return SafetyController(camera_service=camera_service, gemini_service=gemini_service, db=db)

@router.post("/analyze", response_model=SafetyAnalyzeResponse)
def analyze_safety(
    payload: SafetyAnalyzeRequest,
    controller: SafetyController = Depends(get_safety_controller)
):
    try:
        return controller.analyze_room(
            consent_given=payload.consent_given,
            image_id=payload.image_id,
            mock_image_key=payload.mock_image_key,
            include_preview=payload.include_preview
        )
    except ConsentRequiredError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except CameraError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except GeminiQuotaExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except GeminiDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
