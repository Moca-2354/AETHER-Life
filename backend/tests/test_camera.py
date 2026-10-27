from fastapi.testclient import TestClient

def test_camera_capture_normal_success(client: TestClient):
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "living_room_normal",
        "include_base64": False
    })
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["format"] == "jpeg"
    assert data["metadata"]["width"] == 640
    assert data["metadata"]["height"] == 480
    assert data["metadata"]["size_bytes"] > 0
    assert data["preview_base64"] is None

def test_camera_capture_png_with_base64(client: TestClient):
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "test_sample_png",
        "include_base64": True
    })
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["format"] == "png"
    assert data["preview_base64"] is not None
    assert len(data["preview_base64"]) > 50

def test_camera_capture_non_existent_key(client: TestClient):
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "non_existent_camera_preset"
    })
    assert response.status_code == 404
    assert "Unknown camera preset key" in response.json()["detail"]

def test_camera_capture_path_traversal_prevention(client: TestClient):
    # Attempt directory traversal attack
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "../../etc/passwd"
    })
    assert response.status_code == 404
    assert "Unknown camera preset key" in response.json()["detail"]

def test_camera_capture_invalid_format(client: TestClient):
    # Text file masquerading as image fixture
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "invalid_format"
    })
    assert response.status_code == 400
    assert "Invalid or corrupted image data" in response.json()["detail"]

def test_camera_capture_corrupted_file(client: TestClient):
    response = client.post("/api/camera/capture", json={
        "mock_image_key": "corrupted"
    })
    assert response.status_code == 400
    assert "corrupted" in response.json()["detail"].lower()
