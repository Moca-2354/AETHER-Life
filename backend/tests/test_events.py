from fastapi.testclient import TestClient

def test_get_events_empty(client: TestClient):
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json() == []

def test_create_and_get_events(client: TestClient):
    # Create test events
    event1 = {
        "event_type": "motion_detected",
        "description": "Living room motion sensor triggered",
        "source": "sensor",
        "payload": '{"sensor_id": "living_01"}'
    }
    event2 = {
        "event_type": "door_opened",
        "description": "Front door opened",
        "source": "sensor",
        "payload": '{"door_id": "front"}'
    }

    res1 = client.post("/api/events", json=event1)
    assert res1.status_code == 201
    created1 = res1.json()
    assert created1["event_type"] == "motion_detected"
    assert created1["id"] is not None

    res2 = client.post("/api/events", json=event2)
    assert res2.status_code == 201

    # Fetch all events (should be ordered descending by created_at / id)
    response = client.get("/api/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "door_opened"
    assert events[1]["event_type"] == "motion_detected"

def test_get_events_filtering_and_pagination(client: TestClient):
    # Insert multiple events
    for i in range(5):
        client.post("/api/events", json={
            "event_type": "type_a" if i % 2 == 0 else "type_b",
            "description": f"Event {i}",
            "source": "system"
        })

    # Test limit
    res_limit = client.get("/api/events?limit=2")
    assert res_limit.status_code == 200
    assert len(res_limit.json()) == 2

    # Test offset
    res_offset = client.get("/api/events?limit=2&offset=2")
    assert res_offset.status_code == 200
    assert len(res_offset.json()) == 2

    # Test filter by event_type
    res_filtered = client.get("/api/events?event_type=type_b")
    assert res_filtered.status_code == 200
    b_events = res_filtered.json()
    assert len(b_events) == 2
    assert all(e["event_type"] == "type_b" for e in b_events)
