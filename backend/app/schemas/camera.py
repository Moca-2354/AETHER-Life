from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CameraImageMetadata(BaseModel):
    image_id: str = Field(..., description="Unique ID for the captured image")
    format: str = Field(..., description="Image format (jpeg, png)")
    width: int = Field(..., description="Width in pixels")
    height: int = Field(..., description="Height in pixels")
    size_bytes: int = Field(..., description="Image size in bytes")
    captured_at: datetime = Field(..., description="Timestamp of capture")

class CameraCaptureRequest(BaseModel):
    mock_image_key: Optional[str] = Field(
        default="living_room_normal",
        description="Preset key for Mock camera (e.g. living_room_normal, living_room_cluttered, living_room_fall_hazard)"
    )
    include_base64: bool = Field(
        default=False,
        description="Whether to include base64-encoded image string in response"
    )

class CameraCaptureResponse(BaseModel):
    metadata: CameraImageMetadata
    preview_base64: Optional[str] = Field(
        default=None,
        description="Base64 encoded image preview if requested"
    )
