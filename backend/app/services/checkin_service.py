import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.checkin import Checkin, CheckinStatus
from app.models.notification_log import NotificationType
from app.schemas.checkin import CheckinCreate
from app.services.event_service import EventService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class CheckinNotFoundError(Exception):
    pass

class CheckinInvalidStatusError(Exception):
    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__(f"Checkin is already {current_status}")

class CheckinDuplicateError(Exception):
    def __init__(self, slot_key: str):
        self.slot_key = slot_key
        super().__init__(f"Checkin for slot '{slot_key}' already exists.")

class CheckinService:
    def __init__(self, db: Session):
        self.db = db
        self.event_service = EventService(db)
        self.notification_service = NotificationService(db)

    def get_checkin_by_id(self, checkin_id: int) -> Optional[Checkin]:
        return self.db.get(Checkin, checkin_id)

    def expire_checkin(self, checkin_id: int) -> bool:
        """
        Atomically marks a checkin as expired if it is still pending and past due.
        Updates status and logs checkin_expired in the same transaction.
        After commit, dispatches family notification (mock).
        """
        now = datetime.now(timezone.utc)
        try:
            # Atomic UPDATE with synchronize_session=False to avoid SQLite timezone evaluator issues
            stmt = (
                update(Checkin)
                .where(
                    Checkin.id == checkin_id,
                    Checkin.status == CheckinStatus.PENDING.value,
                    Checkin.expires_at.is_not(None),
                    Checkin.expires_at <= now
                )
                .values(
                    status=CheckinStatus.EXPIRED.value,
                    updated_at=now
                )
                .execution_options(synchronize_session=False)
            )
            result = self.db.execute(stmt)
            if result.rowcount == 0:
                self.db.rollback()
                return False

            # Record checkin_expired event in the same transaction
            self.event_service.log_event(
                event_type="checkin_expired",
                description=f"Checkin {checkin_id} expired without response",
                source="system",
                payload=json.dumps({"checkin_id": checkin_id}),
                auto_commit=False
            )

            # Commit both status change and event atomically
            self.db.commit()
            logger.info(f"[CheckinService] Checkin {checkin_id} expired successfully.")
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CheckinService] Error expiring checkin {checkin_id}: {e}")
            raise

        # Dispatch family notification Mock AFTER successful DB commit
        try:
            self.notification_service.send_notification(
                checkin_id=checkin_id,
                notification_type=NotificationType.FAMILY_UNRESPONSIVE_ALERT,
                destination="family_emergency_contact"
            )
        except Exception as notif_err:
            logger.error(f"[CheckinService] Notification failed for expired checkin {checkin_id}: {notif_err}")

        return True

    def expire_all_pending_due(self) -> List[int]:
        """
        Actively scans and expires all pending checkins that have passed their expiration time.
        Used by background scheduler and startup recovery.
        """
        now = datetime.now(timezone.utc)
        query = (
            select(Checkin.id, Checkin.expires_at)
            .where(
                Checkin.status == CheckinStatus.PENDING.value,
                Checkin.expires_at.is_not(None)
            )
            .order_by(Checkin.id.asc())
        )
        rows = list(self.db.execute(query).all())
        expired_ids = []
        for cid, exp_at in rows:
            normalized_exp = ensure_utc(exp_at)
            if normalized_exp and normalized_exp <= now:
                if self.expire_checkin(cid):
                    expired_ids.append(cid)
        return expired_ids

    def get_current_pending_checkin(self) -> Optional[Checkin]:
        """
        Fetches the latest active pending checkin.
        Expired checkins are actively updated and skipped.
        """
        now = datetime.now(timezone.utc)
        query = (
            select(Checkin)
            .where(Checkin.status == CheckinStatus.PENDING.value)
            .order_by(Checkin.created_at.desc(), Checkin.id.desc())
        )
        checkins = list(self.db.scalars(query).all())
        for checkin in checkins:
            exp_at = ensure_utc(checkin.expires_at)
            if exp_at is not None and exp_at <= now:
                self.expire_checkin(checkin.id)
                continue
            return checkin
        return None

    def create_checkin(
        self,
        checkin_in: CheckinCreate,
        slot_key: Optional[str] = None,
        send_notification: bool = True,
        simulate_notification_failure: bool = False
    ) -> Checkin:
        """
        Creates a new checkin.
        Guarantees idempotency via unique slot_key if provided.
        Checkin and event are committed together. Mock notification is dispatched after commit.
        """
        target_slot_key = slot_key or checkin_in.slot_key

        if target_slot_key:
            existing = self.db.scalar(
                select(Checkin).where(Checkin.slot_key == target_slot_key)
            )
            if existing:
                raise CheckinDuplicateError(target_slot_key)

        try:
            checkin = Checkin(
                prompt_message=checkin_in.prompt_message,
                expires_at=ensure_utc(checkin_in.expires_at),
                slot_key=target_slot_key,
                status=CheckinStatus.PENDING.value
            )
            self.db.add(checkin)
            self.db.flush()

            # Record event in the same transaction
            self.event_service.log_event(
                event_type="checkin_created",
                description=f"Checkin requested: {checkin.prompt_message}",
                source="system",
                payload=json.dumps({"checkin_id": checkin.id, "slot_key": target_slot_key}),
                auto_commit=False
            )

            # Atomic commit of checkin and checkin_created event
            self.db.commit()
            self.db.refresh(checkin)
        except IntegrityError:
            self.db.rollback()
            raise CheckinDuplicateError(target_slot_key or "duplicate")
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CheckinService] Failed to create checkin: {e}")
            raise

        # Dispatch mock user notification AFTER commit
        if send_notification:
            try:
                self.notification_service.send_notification(
                    checkin_id=checkin.id,
                    notification_type=NotificationType.USER_PROMPT,
                    destination="user_primary_device",
                    simulate_failure=simulate_notification_failure
                )
            except Exception as notif_err:
                logger.error(f"[CheckinService] User notification failed for checkin {checkin.id}: {notif_err}")

        return checkin

    def respond_to_checkin(
        self,
        checkin_id: Optional[int],
        response_message: str
    ) -> Checkin:
        """
        Atomically responds to a checkin.
        Validates that checkin exists, is pending, and has NOT expired (expires_at > now).
        State change and checkin_responded event are committed atomically.
        """
        now = datetime.now(timezone.utc)

        # 1. Resolve target ID
        if checkin_id is not None:
            target_id = checkin_id
            existing = self.get_checkin_by_id(target_id)
            if not existing:
                raise CheckinNotFoundError("Checkin not found")
        else:
            current = self.get_current_pending_checkin()
            if not current:
                raise CheckinNotFoundError("No active pending checkin found")
            target_id = current.id
            existing = current

        # Pre-check expiration
        exp_at = ensure_utc(existing.expires_at)
        if exp_at is not None and exp_at <= now:
            self.expire_checkin(existing.id)
            raise CheckinInvalidStatusError(CheckinStatus.EXPIRED.value)

        if existing.status != CheckinStatus.PENDING.value:
            raise CheckinInvalidStatusError(existing.status)

        # 2. Atomic conditional update: status == pending AND (expires_at IS NULL OR expires_at > now)
        try:
            stmt = (
                update(Checkin)
                .where(
                    Checkin.id == target_id,
                    Checkin.status == CheckinStatus.PENDING.value,
                    or_(Checkin.expires_at.is_(None), Checkin.expires_at > now)
                )
                .values(
                    status=CheckinStatus.RESPONDED.value,
                    response_message=response_message,
                    responded_at=now,
                    updated_at=now
                )
                .execution_options(synchronize_session=False)
            )
            result = self.db.execute(stmt)
            if result.rowcount == 0:
                self.db.rollback()
                rechecked = self.get_checkin_by_id(target_id)
                if rechecked:
                    raise CheckinInvalidStatusError(rechecked.status)
                raise CheckinNotFoundError("Checkin not found")

            # 3. Log event in the same transaction
            self.event_service.log_event(
                event_type="checkin_responded",
                description=f"Checkin answered: {response_message}",
                source="user",
                payload=json.dumps({"checkin_id": target_id}),
                auto_commit=False
            )

            # 4. Atomic commit of checkin state and event
            self.db.commit()
            self.db.expire(existing)
            self.db.refresh(existing)
        except Exception as e:
            self.db.rollback()
            if not isinstance(e, (CheckinNotFoundError, CheckinInvalidStatusError)):
                logger.error(f"[CheckinService] Error responding to checkin {target_id}: {e}")
            raise

        # 5. Dispatch optional resolution notification Mock AFTER commit
        try:
            self.notification_service.send_notification(
                checkin_id=target_id,
                notification_type=NotificationType.RESOLUTION,
                destination="user_and_family"
            )
        except Exception as notif_err:
            logger.error(f"[CheckinService] Resolution notification failed for checkin {target_id}: {notif_err}")

        return existing
