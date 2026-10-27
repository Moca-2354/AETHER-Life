import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.notification_log import NotificationLog, NotificationType, NotificationStatus

logger = logging.getLogger(__name__)

class NotificationResult:
    def __init__(self, success: bool, message_id: Optional[str] = None, error_message: Optional[str] = None, skipped: bool = False):
        self.success = success
        self.message_id = message_id
        self.error_message = error_message
        self.skipped = skipped

class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def send_notification(
        self,
        checkin_id: int,
        notification_type: NotificationType,
        destination: Optional[str] = None,
        simulate_failure: bool = False
    ) -> NotificationResult:
        """
        Sends a mock notification and records the result in NotificationLog.
        Ensures idempotent notification dispatch (prevents duplicates).
        """
        # 1. Check for existing successful notification of the same type for this checkin
        existing = self.db.scalar(
            select(NotificationLog).where(
                NotificationLog.checkin_id == checkin_id,
                NotificationLog.notification_type == notification_type.value,
                NotificationLog.status == NotificationStatus.SENT.value
            )
        )
        if existing:
            logger.info(
                f"[NotificationService] Notification already sent for checkin {checkin_id} and type {notification_type.value}. Skipping."
            )
            return NotificationResult(success=True, message_id=existing.message_id, skipped=True)

        # 2. Simulate notification dispatch (Mock)
        if simulate_failure:
            status = NotificationStatus.FAILED.value
            message_id = None
            error_message = "Mock dispatch error: push notification provider unreachable"
            logger.warning(
                f"[NotificationService Mock FAILED] checkin_id={checkin_id}, type={notification_type.value}, error={error_message}"
            )
        else:
            status = NotificationStatus.SENT.value
            message_id = f"mock-msg-{uuid.uuid4().hex[:8]}"
            error_message = None
            logger.info(
                f"[NotificationService Mock SENT] checkin_id={checkin_id}, type={notification_type.value}, dest={destination}, msg_id={message_id}"
            )

        # 3. Record in NotificationLog and commit independently
        log_entry = NotificationLog(
            checkin_id=checkin_id,
            notification_type=notification_type.value,
            status=status,
            destination=destination or "mock_device_target",
            message_id=message_id,
            error_message=error_message
        )
        self.db.add(log_entry)
        try:
            self.db.commit()
            self.db.refresh(log_entry)
        except Exception as e:
            self.db.rollback()
            logger.error(f"[NotificationService] Failed to commit notification log: {e}")
            return NotificationResult(success=False, error_message=str(e))

        return NotificationResult(
            success=(status == NotificationStatus.SENT.value),
            message_id=message_id,
            error_message=error_message,
            skipped=False
        )
