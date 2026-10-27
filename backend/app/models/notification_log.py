from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.checkin import Checkin

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class NotificationType(str, Enum):
    USER_PROMPT = "user_prompt"
    FAMILY_UNRESPONSIVE_ALERT = "family_unresponsive_alert"
    RESOLUTION = "resolution"

class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("checkins.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=NotificationStatus.SENT.value)
    destination: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    checkin: Mapped["Checkin"] = relationship("Checkin", back_populates="notification_logs")
