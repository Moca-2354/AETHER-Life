from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.notification_log import NotificationLog

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CheckinStatus(str, Enum):
    PENDING = "pending"
    RESPONDED = "responded"
    EXPIRED = "expired"

class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CheckinStatus.PENDING.value,
        index=True
    )
    prompt_message: Mapped[str] = mapped_column(String(255), nullable=False)
    response_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    slot_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now
    )

    notification_logs: Mapped[List["NotificationLog"]] = relationship(
        "NotificationLog",
        back_populates="checkin",
        cascade="all, delete-orphan",
        order_by="NotificationLog.sent_at.desc()"
    )
