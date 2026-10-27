from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

def test_get_current_checkin_when_empty(client: TestClient):
    response = client.get("/api/checkins/current")
    assert response.status_code == 200
    assert response.json() is None

def test_get_current_checkin_and_respond(client: TestClient):
    # Create a pending checkin
    checkin_data = {
        "prompt_message": "おはようございます。体調はいかがですか？",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    }
    create_res = client.post("/api/checkins", json=checkin_data)
    assert create_res.status_code == 201
    checkin = create_res.json()
    assert checkin["status"] == "pending"
    assert checkin["prompt_message"] == checkin_data["prompt_message"]

    # Verify checkin_created event was logged
    events_res = client.get("/api/events?event_type=checkin_created")
    assert events_res.status_code == 200
    assert len(events_res.json()) >= 1

    # GET /api/checkins/current should return this checkin
    current_res = client.get("/api/checkins/current")
    assert current_res.status_code == 200
    current_data = current_res.json()
    assert current_data is not None
    assert current_data["id"] == checkin["id"]
    assert current_data["status"] == "pending"

    # POST /api/checkins/respond without checkin_id (targets current pending)
    respond_data = {
        "response_message": "問題ありません。元気です。"
    }
    respond_res = client.post("/api/checkins/respond", json=respond_data)
    assert respond_res.status_code == 200
    responded_checkin = respond_res.json()
    assert responded_checkin["id"] == checkin["id"]
    assert responded_checkin["status"] == "responded"
    assert responded_checkin["response_message"] == "問題ありません。元気です。"
    assert responded_checkin["responded_at"] is not None

    # Current pending checkin should now be None
    current_res2 = client.get("/api/checkins/current")
    assert current_res2.status_code == 200
    assert current_res2.json() is None

    # Verify checkin_responded event was logged
    events_res2 = client.get("/api/events?event_type=checkin_responded")
    assert events_res2.status_code == 200
    responded_events = events_res2.json()
    assert len(responded_events) >= 1
    assert "問題ありません。元気です。" in responded_events[0]["description"]

def test_respond_to_specific_checkin_and_duplicate_response(client: TestClient):
    create_res = client.post("/api/checkins", json={
        "prompt_message": "午後の安否確認です。"
    })
    checkin_id = create_res.json()["id"]

    # First respond with explicit checkin_id
    res1 = client.post("/api/checkins/respond", json={
        "checkin_id": checkin_id,
        "response_message": "良好"
    })
    assert res1.status_code == 200
    assert res1.json()["status"] == "responded"

    # Second respond to already responded checkin should return 400
    res2 = client.post("/api/checkins/respond", json={
        "checkin_id": checkin_id,
        "response_message": "再度送信"
    })
    assert res2.status_code == 400
    assert "already responded" in res2.json()["detail"]

def test_respond_non_existent_checkin(client: TestClient):
    res = client.post("/api/checkins/respond", json={
        "checkin_id": 99999,
        "response_message": "test"
    })
    assert res.status_code == 404
    assert "Checkin not found" in res.json()["detail"]

def test_respond_when_no_pending_checkin(client: TestClient):
    res = client.post("/api/checkins/respond", json={
        "response_message": "test"
    })
    assert res.status_code == 404
    assert "No active pending checkin found" in res.json()["detail"]

def test_checkin_expired(client: TestClient):
    # Create an expired checkin
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    create_res = client.post("/api/checkins", json={
        "prompt_message": "過去のチェックイン",
        "expires_at": past_time
    })
    expired_id = create_res.json()["id"]

    # GET /api/checkins/current should recognize expiration and return None
    current_res = client.get("/api/checkins/current")
    assert current_res.status_code == 200
    assert current_res.json() is None

    # Responding to expired checkin should fail with 400
    respond_res = client.post("/api/checkins/respond", json={
        "checkin_id": expired_id,
        "response_message": "遅れて回答"
    })
    assert respond_res.status_code == 400
    assert "already expired" in respond_res.json()["detail"]
