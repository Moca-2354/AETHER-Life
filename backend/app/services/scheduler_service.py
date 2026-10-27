import logging
from datetime import datetime, timezone, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.checkin import CheckinCreate
from app.services.checkin_service import CheckinService, CheckinDuplicateError

logger = logging.getLogger(__name__)

class CheckinScheduler:
    def __init__(self):
        tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
        self.scheduler = BackgroundScheduler(timezone=tz)
        self._is_running = False

    def startup_recovery(self):
        """
        Runs once synchronously upon application startup.
        Scans and expires all checkins that passed their expiration during system downtime.
        """
        logger.info("[CheckinScheduler] Running startup recovery for expired checkins...")
        db = SessionLocal()
        try:
            service = CheckinService(db)
            expired_ids = service.expire_all_pending_due()
            if expired_ids:
                logger.info(f"[CheckinScheduler] Recovered {len(expired_ids)} expired checkin(s): {expired_ids}")
            else:
                logger.info("[CheckinScheduler] No overdue pending checkins found during recovery.")
        except Exception as e:
            logger.error(f"[CheckinScheduler] Startup recovery failed: {e}")
        finally:
            db.close()

    def generate_scheduled_checkin_job(self):
        """
        Scheduled job to automatically generate a daily/periodic checkin.
        Prevents duplicates using slot_key and max_instances=1.
        """
        tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
        now_local = datetime.now(tz)
        slot_key = now_local.strftime("%Y-%m-%d_%H:%M")

        logger.info(f"[CheckinScheduler] Executing scheduled checkin job for slot: {slot_key}")
        db = SessionLocal()
        try:
            service = CheckinService(db)

            # Prevent duplicate generation if there is already an active pending checkin
            current_pending = service.get_current_pending_checkin()
            if current_pending:
                logger.warning(
                    f"[CheckinScheduler] Active pending checkin (ID={current_pending.id}) already exists. Skipping slot {slot_key}."
                )
                return

            expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.CHECKIN_DEFAULT_TIMEOUT_MINUTES)
            checkin_in = CheckinCreate(
                prompt_message="定期の安否確認です。体調はいかがですか？",
                expires_at=expires_at,
                slot_key=slot_key
            )
            created = service.create_checkin(checkin_in, slot_key=slot_key)
            logger.info(f"[CheckinScheduler] Successfully created scheduled checkin ID={created.id} (slot={slot_key})")
        except CheckinDuplicateError:
            logger.info(f"[CheckinScheduler] Checkin for slot {slot_key} already exists. Skipping.")
        except Exception as e:
            logger.error(f"[CheckinScheduler] Failed generating scheduled checkin for slot {slot_key}: {e}")
        finally:
            db.close()

    def check_expired_checkins_job(self):
        """
        Interval job running actively in the background to detect and expire overdue checkins.
        """
        db = SessionLocal()
        try:
            service = CheckinService(db)
            expired_ids = service.expire_all_pending_due()
            if expired_ids:
                logger.info(f"[CheckinScheduler] Expired {len(expired_ids)} overdue checkin(s): {expired_ids}")
        except Exception as e:
            logger.error(f"[CheckinScheduler] Periodic expiration check failed: {e}")
        finally:
            db.close()

    def start(self):
        if not settings.CHECKIN_SCHEDULER_ENABLED:
            logger.info("[CheckinScheduler] Scheduler is disabled via configuration.")
            return

        if self._is_running:
            logger.warning("[CheckinScheduler] Scheduler is already running.")
            return

        # 1. Execute startup recovery before scheduling new jobs
        self.startup_recovery()

        # 2. Register scheduled checkin creation (Cron)
        # Supports standard cron: "minute hour day month day_of_week"
        cron_parts = settings.CHECKIN_SCHEDULE_CRON.split()
        if len(cron_parts) == 5:
            cron_trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
                timezone=pytz.timezone(settings.SCHEDULER_TIMEZONE)
            )
        else:
            cron_trigger = CronTrigger.from_crontab(
                settings.CHECKIN_SCHEDULE_CRON,
                timezone=pytz.timezone(settings.SCHEDULER_TIMEZONE)
            )

        self.scheduler.add_job(
            self.generate_scheduled_checkin_job,
            trigger=cron_trigger,
            id="generate_scheduled_checkin",
            name="Generate Scheduled Checkin",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            replace_existing=True
        )

        # 3. Register periodic active expiration check (Interval)
        interval_trigger = IntervalTrigger(
            seconds=settings.CHECKIN_EXPIRATION_CHECK_INTERVAL_SECONDS,
            timezone=pytz.timezone(settings.SCHEDULER_TIMEZONE)
        )
        self.scheduler.add_job(
            self.check_expired_checkins_job,
            trigger=interval_trigger,
            id="check_expired_checkins",
            name="Check Expired Checkins",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
            replace_existing=True
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("[CheckinScheduler] APScheduler started successfully.")

    def shutdown(self):
        if self._is_running:
            logger.info("[CheckinScheduler] Shutting down APScheduler...")
            self.scheduler.shutdown(wait=False)
            self._is_running = False

checkin_scheduler = CheckinScheduler()
