from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class GeminiUsageLog(Base):
    __tablename__ = "gemini_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )
