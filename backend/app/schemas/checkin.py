from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.checkin import CheckinStatus

class CheckinBase(BaseModel):
    prompt_message: str = Field(..., max_length=255, description="Prompt message for checkin")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration time")

class CheckinCreate(CheckinBase):
    pass

class CheckinRespondRequest(BaseModel):
    checkin_id: Optional[int] = Field(default=None, description="ID of checkin to respond to. If None, targets the current pending checkin.")
    response_message: str = Field(..., min_length=1, description="Response message from user")

class CheckinResponse(BaseModel):
    id: int
    status: CheckinStatus
    prompt_message: str
    response_message: Optional[str] = None
    responded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
