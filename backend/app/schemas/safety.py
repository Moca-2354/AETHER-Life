from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.camera import CameraImageMetadata

class SafetyRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"

class HazardItem(BaseModel):
    category: str = Field(..., description="Category of hazard (e.g. fall_hazard, obstacle, posture, lighting)")
    description: str = Field(..., description="Detailed description of the observed hazard")
    location_hint: Optional[str] = Field(default=None, description="Location in room (e.g. bed side, hallway)")
    severity: str = Field(..., description="low | medium | high")

class RoomSafetyAnalysis(BaseModel):
    risk_level: SafetyRiskLevel = Field(..., description="Overall room safety risk level")
    summary: str = Field(..., description="Concise summary in Japanese")
    observations: List[str] = Field(default_factory=list, description="Observations of the room environment")
    hazards: List[HazardItem] = Field(default_factory=list, description="List of detected hazard candidates")
    recommendations: List[str] = Field(default_factory=list, description="Suggested actions for residents/caregivers")

    model_config = ConfigDict(from_attributes=True)

class GeminiUsageMetadata(BaseModel):
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    is_mock: bool

class SafetyAnalyzeRequest(BaseModel):
    image_id: Optional[str] = Field(
        default=None,
        description="ID of previously captured image. If omitted, captures a new image automatically."
    )
    mock_image_key: Optional[str] = Field(
        default=None,
        description="Preset key when auto-capturing mock image"
    )
    consent_given: bool = Field(
        ...,
        description="Explicit user consent required for cloud image analysis"
    )
    include_preview: bool = Field(
        default=False,
        description="Whether to include base64 preview in response"
    )

class SafetyAnalyzeResponse(BaseModel):
    analysis: RoomSafetyAnalysis
    metadata: CameraImageMetadata
    usage: GeminiUsageMetadata
    event_id: Optional[int] = Field(default=None, description="Event ID logged in life history")
    evaluated_at: datetime
    preview_base64: Optional[str] = None
