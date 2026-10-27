from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.checkin import Checkin, CheckinStatus
from app.schemas.checkin import CheckinCreate
from app.services.event_service import EventService

class CheckinNotFoundError(Exception):
    pass

class CheckinInvalidStatusError(Exception):
    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__(f"Checkin is already {current_status}")

class CheckinService:
    def __init__(self, db: Session):
        self.db = db
        self.event_service = EventService(db)

    def _expire_if_needed(self, checkin: Checkin, now: datetime) -> bool:
        if checkin.expires_at is not None:
            expires_at = checkin.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                checkin.status = CheckinStatus.EXPIRED.value
                self.db.add(checkin)
                self.db.commit()
                self.db.refresh(checkin)
                return True
        return False

    def get_current_pending_checkin(self) -> Optional[Checkin]:
        now = datetime.now(timezone.utc)
        # Find latest pending checkins
        query = (
            select(Checkin)
            .where(Checkin.status == CheckinStatus.PENDING.value)
            .order_by(Checkin.created_at.desc(), Checkin.id.desc())
        )
        checkins = list(self.db.scalars(query).all())
        for checkin in checkins:
            if self._expire_if_needed(checkin, now):
                continue
            return checkin
        return None

    def get_checkin_by_id(self, checkin_id: int) -> Optional[Checkin]:
        return self.db.get(Checkin, checkin_id)

    def create_checkin(self, checkin_in: CheckinCreate) -> Checkin:
        checkin = Checkin(
            prompt_message=checkin_in.prompt_message,
            expires_at=checkin_in.expires_at,
            status=CheckinStatus.PENDING.value
        )
        self.db.add(checkin)
        self.db.commit()
        self.db.refresh(checkin)

        # Log event for checkin creation
        self.event_service.log_event(
            event_type="checkin_created",
            description=f"Checkin requested: {checkin.prompt_message}",
            source="system",
            payload=f'{{"checkin_id": {checkin.id}}}'
        )
        return checkin

    def respond_to_checkin(
        self,
        checkin_id: Optional[int],
        response_message: str
    ) -> Checkin:
        now = datetime.now(timezone.utc)

        if checkin_id is not None:
            checkin = self.get_checkin_by_id(checkin_id)
            if not checkin:
                raise CheckinNotFoundError("Checkin not found")
        else:
            checkin = self.get_current_pending_checkin()
            if not checkin:
                raise CheckinNotFoundError("No active pending checkin found")

        # Check if expired
        if self._expire_if_needed(checkin, now):
            raise CheckinInvalidStatusError(CheckinStatus.EXPIRED.value)

        if checkin.status != CheckinStatus.PENDING.value:
            raise CheckinInvalidStatusError(checkin.status)

        checkin.status = CheckinStatus.RESPONDED.value
        checkin.response_message = response_message
        checkin.responded_at = now
        self.db.add(checkin)
        self.db.commit()
        self.db.refresh(checkin)

        # Automatically log checkin response event
        self.event_service.log_event(
            event_type="checkin_responded",
            description=f"Checkin answered: {response_message}",
            source="user",
            payload=f'{{"checkin_id": {checkin.id}}}'
        )

        return checkin
