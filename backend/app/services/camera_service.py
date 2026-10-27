import os
import io
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from PIL import Image, UnidentifiedImageError
from app.core.config import settings
from app.schemas.camera import CameraImageMetadata

class CameraError(Exception):
    pass

class CameraImageNotFoundError(CameraError):
    pass

class CameraInvalidFormatError(CameraError):
    pass

class CameraFileTooLargeError(CameraError):
    pass

class CameraCaptureResult:
    def __init__(self, image_bytes: bytes, metadata: CameraImageMetadata):
        self.image_bytes = image_bytes
        self.metadata = metadata

class CameraService(ABC):
    """
    Abstract interface for room cameras (MockCamera, PiCamera, etc.).
    """
    @abstractmethod
    def capture(self, preset_key: Optional[str] = None) -> CameraCaptureResult:
        """Captures an image and returns raw bytes and metadata."""
        pass

    @abstractmethod
    def get_image(self, image_id: str) -> Optional[CameraCaptureResult]:
        """Retrieves a previously captured image by ID from short-term memory."""
        pass

class MockCameraService(CameraService):
    """
    Mock Camera Service that reads pre-configured test fixtures safely.
    Strictly prevents path traversal by using a fixed whitelist dictionary.
    """
    # Allowed presets mapped to filenames inside fixtures directory
    PRESET_WHITELIST: Dict[str, str] = {
        "living_room_normal": "living_room_normal.jpg",
        "living_room_cluttered": "living_room_cluttered.jpg",
        "living_room_fall_hazard": "living_room_fall_hazard.jpg",
        "test_sample_png": "test_sample.png",
        "corrupted": "corrupted.jpg",
        "invalid_format": "invalid_format.txt"
    }
    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB limit

    def __init__(self, fixtures_dir: Optional[str] = None):
        # Resolve fixtures directory safely relative to project root or config
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.fixtures_dir = fixtures_dir or os.path.join(base_dir, settings.MOCK_CAMERA_DIR)
        # In-memory storage for captured images (short-term cache)
        self._captured_cache: Dict[str, CameraCaptureResult] = {}

    def _validate_image_bytes(self, data: bytes) -> Tuple[str, int, int]:
        """Validates format (JPEG/PNG), dimensions, and size integrity."""
        if len(data) > self.MAX_SIZE_BYTES:
            raise CameraFileTooLargeError(f"Image size exceeds limit of {self.MAX_SIZE_BYTES} bytes")

        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt = (img.format or "").lower()
                if fmt not in ("jpeg", "png"):
                    raise CameraInvalidFormatError(f"Unsupported image format: '{fmt}'. Only JPEG and PNG are allowed.")
                width, height = img.size
                # Verify image can be parsed completely
                img.verify()
                return fmt, width, height
        except (UnidentifiedImageError, OSError, SyntaxError) as e:
            raise CameraInvalidFormatError(f"Invalid or corrupted image data: {e}")

    def capture(self, preset_key: Optional[str] = None) -> CameraCaptureResult:
        key = preset_key or "living_room_normal"
        if key not in self.PRESET_WHITELIST:
            raise CameraImageNotFoundError(
                f"Unknown camera preset key '{key}'. Allowed presets: {list(self.PRESET_WHITELIST.keys())}"
            )

        filename = self.PRESET_WHITELIST[key]
        filepath = os.path.join(self.fixtures_dir, filename)

        if not os.path.exists(filepath):
            raise CameraImageNotFoundError(f"Fixture image file not found at: {filepath}")

        with open(filepath, "rb") as f:
            data = f.read()

        fmt, width, height = self._validate_image_bytes(data)

        image_id = str(uuid.uuid4())
        metadata = CameraImageMetadata(
            image_id=image_id,
            format=fmt,
            width=width,
            height=height,
            size_bytes=len(data),
            captured_at=datetime.now(timezone.utc)
        )
        result = CameraCaptureResult(image_bytes=data, metadata=metadata)
        self._captured_cache[image_id] = result
        return result

    def get_image(self, image_id: str) -> Optional[CameraCaptureResult]:
        return self._captured_cache.get(image_id)

class PiCameraService(CameraService):
    """
    Placeholder for future Raspberry Pi Camera Module integration.
    """
    def capture(self, preset_key: Optional[str] = None) -> CameraCaptureResult:
        raise NotImplementedError("PiCameraService is not yet implemented on this platform.")

    def get_image(self, image_id: str) -> Optional[CameraCaptureResult]:
        raise NotImplementedError("PiCameraService is not yet implemented on this platform.")

# Singleton instance for mock camera service
mock_camera_service = MockCameraService()

def get_camera_service() -> CameraService:
    return mock_camera_service
