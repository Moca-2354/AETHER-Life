import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.checkin import Checkin, CheckinStatus
from app.models.notification_log import NotificationLog, NotificationType, NotificationStatus
from app.models.event import Event
from app.schemas.checkin import CheckinCreate
from app.services.checkin_service import (
    CheckinService,
    CheckinInvalidStatusError,
    CheckinDuplicateError,
)
from app.services.notification_service import NotificationService
from app.services.scheduler_service import checkin_scheduler


def test_respond_just_before_expiration(client: TestClient, db_session: Session):
    """
    検証項目: 期限切れ直前の応答
    有効期限まで残り僅か（例: 10秒）であっても、期限内であれば応答が正常に受理されること。
    """
    now = datetime.now(timezone.utc)
    service = CheckinService(db_session)
    checkin = service.create_checkin(CheckinCreate(
        prompt_message="期限切れ直前テスト",
        expires_at=now + timedelta(seconds=10)
    ))

    # Respond via API
    res = client.post("/api/checkins/respond", json={
        "checkin_id": checkin.id,
        "response_message": "ギリギリ間に合いました"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "responded"
    assert res.json()["response_message"] == "ギリギリ間に合いました"


def test_reject_response_after_expiration(client: TestClient, db_session: Session):
    """
    検証項目: 期限切れ後の応答拒否
    すでに期限（expires_at）を過ぎたCheckinへの応答は 400 で拒否され、status が expired になること。
    """
    now = datetime.now(timezone.utc)
    service = CheckinService(db_session)
    checkin = service.create_checkin(CheckinCreate(
        prompt_message="期限切れ後テスト",
        expires_at=now - timedelta(seconds=1)
    ))

    # Attempt to respond to expired checkin
    res = client.post("/api/checkins/respond", json={
        "checkin_id": checkin.id,
        "response_message": "遅れました"
    })
    assert res.status_code == 400
    assert "already expired" in res.json()["detail"]

    # Verify checkin is expired in DB
    refreshed = service.get_checkin_by_id(checkin.id)
    assert refreshed.status == CheckinStatus.EXPIRED.value


def test_duplicate_checkin_prevention(client: TestClient, db_session: Session):
    """
    検証項目: Checkinの重複生成防止
    同一の slot_key を用いてCheckinを二重生成しようとした場合、409 Conflictで弾かれること。
    """
    slot_key = "2026-10-27_09:00"
    payload = {
        "prompt_message": "朝の確認",
        "slot_key": slot_key
    }

    # 1st creation: Success
    res1 = client.post("/api/checkins", json=payload)
    assert res1.status_code == 201
    assert res1.json()["slot_key"] == slot_key

    # 2nd creation: Rejected due to unique slot_key
    res2 = client.post("/api/checkins", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


def test_notification_failure_resilience(db_session: Session):
    """
    検証項目: 通知失敗時のDB整合性
    通知配送が失敗しても、Checkin 本体の生成・状態はロールバックされず pending として維持されること。
    """
    service = CheckinService(db_session)
    now = datetime.now(timezone.utc)

    # Create checkin simulating notification failure
    checkin = service.create_checkin(
        CheckinCreate(
            prompt_message="通知障害テスト",
            expires_at=now + timedelta(hours=1),
            slot_key="test_notif_fail_slot"
        ),
        simulate_notification_failure=True
    )

    # Checkin must exist and be pending
    assert checkin.id is not None
    assert checkin.status == CheckinStatus.PENDING.value

    # NotificationLog must record FAILED status
    notif_log = db_session.query(NotificationLog).filter_by(checkin_id=checkin.id).first()
    assert notif_log is not None
    assert notif_log.status == NotificationStatus.FAILED.value
    assert "unreachable" in notif_log.error_message


def test_event_logging_failure_rollback(db_session: Session):
    """
    検証項目: Event記録失敗時のロールバック
    Checkin状態更新時にEvent記録で予期せぬ例外が発生した場合、Checkinのステータス更新もロールバックされること。
    """
    service = CheckinService(db_session)
    now = datetime.now(timezone.utc)

    checkin = service.create_checkin(CheckinCreate(
        prompt_message="ロールバック検証",
        expires_at=now + timedelta(hours=1)
    ))

    # Mock EventService.log_event to raise an exception during respond_to_checkin
    with patch.object(service.event_service, "log_event", side_effect=RuntimeError("Disk full / Event logging failure")):
        with pytest.raises(RuntimeError):
            service.respond_to_checkin(checkin.id, "応答メッセージ")

    # Verify checkin status remains PENDING in DB
    db_session.rollback()
    refreshed = service.get_checkin_by_id(checkin.id)
    assert refreshed.status == CheckinStatus.PENDING.value
    assert refreshed.response_message is None


def test_startup_recovery(db_session: Session):
    """
    検証項目: Scheduler再起動時の復旧
    サーバ停止中に期限を迎えた複数の未処理 pending Checkin が、startup_recovery で一括 expired になること。
    """
    service = CheckinService(db_session)
    past = datetime.now(timezone.utc) - timedelta(minutes=30)

    # Create 3 checkins directly
    c1 = Checkin(prompt_message="停止中期限切れ1", expires_at=past, status=CheckinStatus.PENDING.value)
    c2 = Checkin(prompt_message="停止中期限切れ2", expires_at=past, status=CheckinStatus.PENDING.value)
    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    c3 = Checkin(prompt_message="有効なチェックイン", expires_at=future, status=CheckinStatus.PENDING.value)

    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # Run expire_all_pending_due (which is what startup_recovery executes)
    expired_ids = service.expire_all_pending_due()

    assert len(expired_ids) == 2
    assert c1.id in expired_ids
    assert c2.id in expired_ids
    assert c3.id not in expired_ids

    # Verify status in DB
    assert service.get_checkin_by_id(c1.id).status == CheckinStatus.EXPIRED.value
    assert service.get_checkin_by_id(c2.id).status == CheckinStatus.EXPIRED.value
    assert service.get_checkin_by_id(c3.id).status == CheckinStatus.PENDING.value

    # Verify checkin_expired events were logged
    events = db_session.query(Event).filter_by(event_type="checkin_expired").all()
    assert len(events) == 2


def test_notification_deduplication(db_session: Session):
    """
    検証項目: 通知処理の重複防止
    同一 Checkin に対し同じ通知タイプを送信しようとしても、二重送信されずスキップされること。
    """
    service = CheckinService(db_session)
    notif_service = NotificationService(db_session)

    checkin = service.create_checkin(CheckinCreate(
        prompt_message="通知重複検証"
    ), send_notification=False)

    # First dispatch: Success
    res1 = notif_service.send_notification(
        checkin_id=checkin.id,
        notification_type=NotificationType.USER_PROMPT,
        destination="device_token_abc"
    )
    assert res1.success is True
    assert res1.skipped is False

    # Second dispatch: Skipped
    res2 = notif_service.send_notification(
        checkin_id=checkin.id,
        notification_type=NotificationType.USER_PROMPT,
        destination="device_token_abc"
    )
    assert res2.success is True
    assert res2.skipped is True

    # DB contains only 1 record
    logs = db_session.query(NotificationLog).filter_by(
        checkin_id=checkin.id,
        notification_type=NotificationType.USER_PROMPT.value
    ).all()
    assert len(logs) == 1


def test_scheduler_jobs_execution(db_session: Session):
    """
    検証項目: スケジューラジョブの直接実行テスト
    1. check_expired_checkins_job で期限切れが能動検出されること
    2. generate_scheduled_checkin_job で Checkin が自動生成され、未処理 pending が残っている場合は多重生成がスキップされること
    """
    service = CheckinService(db_session)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)

    overdue = Checkin(prompt_message="期限超過チェックイン", expires_at=past, status=CheckinStatus.PENDING.value)
    db_session.add(overdue)
    db_session.commit()

    # SessionLocal をモックし、かつ close でセッションが破棄されないようにパッチ
    with patch("app.services.scheduler_service.SessionLocal", return_value=db_session), \
         patch.object(db_session, "close", return_value=None):
        # 1. 期限切れ能動監視ジョブ
        checkin_scheduler.check_expired_checkins_job()
        refreshed = service.get_checkin_by_id(overdue.id)
        assert refreshed.status == CheckinStatus.EXPIRED.value

        # 2. 自動生成ジョブの実行（1回目：生成成功）
        checkin_scheduler.generate_scheduled_checkin_job()
        active = service.get_current_pending_checkin()
        assert active is not None
        assert "定期の安否確認" in active.prompt_message

        # 3. 自動生成ジョブの再実行（既に active pending があるためスキップ）
        checkin_scheduler.generate_scheduled_checkin_job()
        pending_list = db_session.query(Checkin).filter_by(status=CheckinStatus.PENDING.value).all()
        assert len(pending_list) == 1
