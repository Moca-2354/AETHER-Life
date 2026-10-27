from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.notification_log import NotificationType, NotificationStatus

class NotificationLogResponse(BaseModel):
    id: int
    checkin_id: int
    notification_type: NotificationType
    status: NotificationStatus
    destination: Optional[str] = None
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)
