from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class EventBase(BaseModel):
    event_type: str = Field(..., max_length=50, description="Type of the event")
    description: str = Field(..., max_length=255, description="Event description")
    source: str = Field(default="system", max_length=50, description="Event source")
    payload: Optional[str] = Field(default=None, description="Optional payload or metadata")

class EventCreate(EventBase):
    pass

class EventResponse(EventBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
