import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.gemini_usage_log import GeminiUsageLog
from app.schemas.camera import CameraImageMetadata
from app.schemas.safety import (
    RoomSafetyAnalysis,
    SafetyRiskLevel,
    GeminiUsageMetadata,
    SafetyAnalyzeResponse,
)
from app.services.camera_service import CameraService, CameraCaptureResult, CameraError
from app.services.gemini_service import (
    GeminiServiceInterface,
    GeminiError,
    GeminiDisabledError,
    GeminiQuotaExceededError,
)
from app.services.event_service import EventService

logger = logging.getLogger(__name__)

class ConsentRequiredError(Exception):
    pass

class SafetyController:
    """
    Orchestrates room capture, privacy verification, Gemini safety evaluation,
    fail-safe unknown fallback, and persistence to Event and Usage logs.
    """
    def __init__(
        self,
        camera_service: CameraService,
        gemini_service: GeminiServiceInterface,
        db: Session
    ):
        self.camera_service = camera_service
        self.gemini_service = gemini_service
        self.db = db
        self.event_service = EventService(db)

    def analyze_room(
        self,
        consent_given: bool,
        image_id: Optional[str] = None,
        mock_image_key: Optional[str] = None,
        include_preview: bool = False
    ) -> SafetyAnalyzeResponse:
        # 1. Enforce privacy consent check
        if not consent_given:
            raise ConsentRequiredError("Explicit user consent is strictly required for room safety image analysis.")

        evaluated_at = datetime.now(timezone.utc)

        # 2. Check daily real API quota against database (ensures safety across restarts & multiple workers)
        if settings.GEMINI_API_ENABLED:
            today_start = evaluated_at.replace(hour=0, minute=0, second=0, microsecond=0)
            real_calls_count = self.db.scalar(
                select(func.count(GeminiUsageLog.id)).where(
                    GeminiUsageLog.is_mock == False,
                    GeminiUsageLog.created_at >= today_start
                )
            ) or 0
            if real_calls_count >= settings.GEMINI_MAX_DAILY_CALLS:
                raise GeminiQuotaExceededError(
                    f"Daily Gemini API limit ({settings.GEMINI_MAX_DAILY_CALLS}) reached in database."
                )

        # 3. Acquire image (from cache or on-demand capture)
        if image_id:
            capture_result = self.camera_service.get_image(image_id)
            if not capture_result:
                raise CameraError(f"Image ID '{image_id}' not found in camera buffer. Please capture a new image.")
        else:
            capture_result = self.camera_service.capture(mock_image_key)

        # 4. Perform AI analysis with fail-safe fallback
        analysis: RoomSafetyAnalysis
        usage: GeminiUsageMetadata
        try:
            analysis, usage = self.gemini_service.analyze_room_safety(
                image_bytes=capture_result.image_bytes,
                image_format=capture_result.metadata.format,
                hint_key=mock_image_key
            )
        except GeminiQuotaExceededError as qe:
            logger.warning(f"[SafetyController] Gemini quota exceeded: {qe}")
            raise
        except GeminiDisabledError as de:
            logger.warning(f"[SafetyController] Gemini disabled: {de}")
            raise
        except (GeminiError, Exception) as ai_err:
            logger.error(f"[SafetyController] AI analysis failed, falling back to 'unknown': {ai_err}")
            analysis = RoomSafetyAnalysis(
                risk_level=SafetyRiskLevel.UNKNOWN,
                summary="AI解析中にエラーが発生したため、判定不能として処理しました。",
                observations=[f"Error detail: {str(ai_err)[:100]}"],
                hazards=[],
                recommendations=["システムの再試行または手動での確認を行ってください。"]
            )
            usage = GeminiUsageMetadata(
                model_id="error_fallback",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
                is_mock=True
            )

        # 5. Record usage metrics into GeminiUsageLog
        try:
            usage_log = GeminiUsageLog(
                model_id=usage.model_id,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
                is_mock=usage.is_mock
            )
            self.db.add(usage_log)

            # 6. Record Safety Event into EventService (same transaction)
            event_payload = json.dumps({
                "image_id": capture_result.metadata.image_id,
                "risk_level": analysis.risk_level.value,
                "hazard_count": len(analysis.hazards),
                "is_mock": usage.is_mock
            })
            logged_event = self.event_service.log_event(
                event_type="safety_analyzed",
                description=f"Room safety analyzed: risk={analysis.risk_level.value} - {analysis.summary[:60]}",
                source="ai_safety_controller",
                payload=event_payload,
                auto_commit=False
            )
            self.db.commit()
            event_id = logged_event.id
        except Exception as db_err:
            self.db.rollback()
            logger.error(f"[SafetyController] Failed to record safety event or usage log: {db_err}")
            event_id = None

        # 7. Prepare preview base64 only if requested
        preview_base64 = None
        if include_preview:
            import base64
            preview_base64 = base64.b64encode(capture_result.image_bytes).decode("utf-8")

        return SafetyAnalyzeResponse(
            analysis=analysis,
            metadata=capture_result.metadata,
            usage=usage,
            event_id=event_id,
            evaluated_at=evaluated_at,
            preview_base64=preview_base64
        )
