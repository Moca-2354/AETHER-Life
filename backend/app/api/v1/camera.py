import base64
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.camera import CameraCaptureRequest, CameraCaptureResponse
from app.services.camera_service import (
    CameraService,
    CameraError,
    CameraImageNotFoundError,
    CameraInvalidFormatError,
    CameraFileTooLargeError,
    get_camera_service,
)

router = APIRouter(prefix="/camera", tags=["camera"])

@router.post("/capture", response_model=CameraCaptureResponse)
def capture_image(
    payload: CameraCaptureRequest,
    camera_service: CameraService = Depends(get_camera_service)
):
    try:
        result = camera_service.capture(payload.mock_image_key)
        preview_base64 = None
        if payload.include_base64:
            preview_base64 = base64.b64encode(result.image_bytes).decode("utf-8")

        return CameraCaptureResponse(
            metadata=result.metadata,
            preview_base64=preview_base64
        )
    except CameraImageNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except (CameraInvalidFormatError, CameraFileTooLargeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except CameraError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
