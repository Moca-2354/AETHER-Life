from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.event import Event
from app.models.gemini_usage_log import GeminiUsageLog
from app.services.gemini_service import GeminiServerError, GeminiResponseInvalidError, GeminiQuotaExceededError
from app.core.config import settings

def test_gemini_api_disabled_by_default():
    """課金防止要件: GEMINI_API_ENABLED がデフォルトで False であることを確認"""
    assert settings.GEMINI_API_ENABLED is False

def test_safety_analyze_normal_room(client: TestClient, db_session: Session):
    response = client.post("/api/safety/analyze", json={
        "mock_image_key": "living_room_normal",
        "consent_given": True,
        "include_preview": False
    })
    assert response.status_code == 200
    data = response.json()
    assert data["analysis"]["risk_level"] == "low"
    assert "良好" in data["analysis"]["summary"] or "整頓" in data["analysis"]["summary"]
    assert data["usage"]["is_mock"] is True
    assert data["usage"]["total_tokens"] > 0
    assert data["usage"]["estimated_cost_usd"] > 0
    assert data["event_id"] is not None

    # Check Event table has recorded safety_analyzed
    event = db_session.get(Event, data["event_id"])
    assert event is not None
    assert event.event_type == "safety_analyzed"
    assert "risk=low" in event.description

    # Check GeminiUsageLog table has recorded usage
    logs = db_session.query(GeminiUsageLog).all()
    assert len(logs) >= 1
    assert logs[-1].is_mock is True

def test_safety_analyze_fall_hazard(client: TestClient, db_session: Session):
    response = client.post("/api/safety/analyze", json={
        "mock_image_key": "living_room_fall_hazard",
        "consent_given": True
    })
    assert response.status_code == 200
    data = response.json()
    assert data["analysis"]["risk_level"] == "high"
    assert len(data["analysis"]["hazards"]) >= 1
    assert data["analysis"]["hazards"][0]["severity"] == "high"

def test_safety_analyze_consent_required(client: TestClient):
    """プライバシー要件: 同意がない場合は 403 Forbidden で解析を遮断"""
    response = client.post("/api/safety/analyze", json={
        "mock_image_key": "living_room_normal",
        "consent_given": False
    })
    assert response.status_code == 403
    assert "consent is strictly required" in response.json()["detail"].lower()

def test_safety_analyze_with_captured_image_id(client: TestClient):
    # 1. Capture image
    cap_res = client.post("/api/camera/capture", json={"mock_image_key": "living_room_cluttered"})
    assert cap_res.status_code == 200
    image_id = cap_res.json()["metadata"]["image_id"]

    # 2. Analyze using image_id
    analyze_res = client.post("/api/safety/analyze", json={
        "image_id": image_id,
        "mock_image_key": "living_room_cluttered",
        "consent_given": True
    })
    assert analyze_res.status_code == 200
    data = analyze_res.json()
    assert data["metadata"]["image_id"] == image_id
    assert data["analysis"]["risk_level"] == "medium"

def test_safety_analyze_gemini_server_error_fallback_to_unknown(client: TestClient, db_session: Session):
    """Gemini API障害・タイムアウト時にフェイルセーフで unknown に倒れること"""
    with patch(
        "app.services.gemini_service.MockGeminiService.analyze_room_safety",
        side_effect=GeminiServerError("503 Service Unavailable / Upstream timeout")
    ):
        response = client.post("/api/safety/analyze", json={
            "mock_image_key": "living_room_normal",
            "consent_given": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["analysis"]["risk_level"] == "unknown"
        assert "エラーが発生したため" in data["analysis"]["summary"]

        # Event should still be recorded with risk=unknown
        event = db_session.get(Event, data["event_id"])
        assert event is not None
        assert "risk=unknown" in event.description

def test_safety_analyze_schema_invalid_fallback_to_unknown(client: TestClient):
    """JSONスキーマ不一致・破損時に unknown に倒れること"""
    with patch(
        "app.services.gemini_service.MockGeminiService.analyze_room_safety",
        side_effect=GeminiResponseInvalidError("Failed to parse Gemini response")
    ):
        response = client.post("/api/safety/analyze", json={
            "mock_image_key": "living_room_normal",
            "consent_given": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["analysis"]["risk_level"] == "unknown"

def test_safety_analyze_quota_exceeded(client: TestClient):
    """課金保護: 日次呼び出し上限超過時に 429 Too Many Requests で遮断"""
    with patch(
        "app.services.gemini_service.MockGeminiService.analyze_room_safety",
        side_effect=GeminiQuotaExceededError("Maximum daily call limit reached")
    ):
        response = client.post("/api/safety/analyze", json={
            "mock_image_key": "living_room_normal",
            "consent_given": True
        })
        assert response.status_code == 429
        assert "Maximum daily call limit reached" in response.json()["detail"]
