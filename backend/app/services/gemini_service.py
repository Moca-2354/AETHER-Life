import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.safety import (
    RoomSafetyAnalysis,
    SafetyRiskLevel,
    HazardItem,
    GeminiUsageMetadata,
)

logger = logging.getLogger(__name__)

class GeminiError(Exception):
    pass

class GeminiDisabledError(GeminiError):
    pass

class GeminiQuotaExceededError(GeminiError):
    pass

class GeminiRateLimitError(GeminiError):
    pass

class GeminiServerError(GeminiError):
    pass

class GeminiResponseInvalidError(GeminiError):
    pass

class GeminiServiceInterface(ABC):
    @abstractmethod
    def analyze_room_safety(
        self,
        image_bytes: bytes,
        image_format: str,
        hint_key: Optional[str] = None
    ) -> Tuple[RoomSafetyAnalysis, GeminiUsageMetadata]:
        pass

class MockGeminiService(GeminiServiceInterface):
    """
    Mock Gemini Service that makes ZERO network calls.
    Guarantees billing prevention and provides deterministic safety evaluations for testing.
    """
    def __init__(self):
        self.call_count = 0

    def analyze_room_safety(
        self,
        image_bytes: bytes,
        image_format: str,
        hint_key: Optional[str] = None
    ) -> Tuple[RoomSafetyAnalysis, GeminiUsageMetadata]:
        self.call_count += 1
        logger.info(f"[MockGeminiService] Executing mock analysis (call #{self.call_count}, hint={hint_key})")

        # Simulate analysis based on preset key or fallback
        if hint_key == "living_room_fall_hazard":
            analysis = RoomSafetyAnalysis(
                risk_level=SafetyRiskLevel.HIGH,
                summary="ベッド横の動線上に大きな障害物があり、転倒の危険性が非常に高い状態です。",
                observations=[
                    "ベッドから立ち上がるスペースに荷物が置かれている",
                    "床に段差およびコードの交差を確認"
                ],
                hazards=[
                    HazardItem(
                        category="fall_hazard",
                        description="動線を塞ぐ大型の荷物と突起物",
                        location_hint="ベッドサイド中央",
                        severity="high"
                    )
                ],
                recommendations=[
                    "ベッド周りの荷物を直ちに移動し、床面を整理してください。",
                    "利用者が移動する際の通路を最低60cm確保してください。"
                ]
            )
        elif hint_key == "living_room_cluttered":
            analysis = RoomSafetyAnalysis(
                risk_level=SafetyRiskLevel.MEDIUM,
                summary="床に衣服や配線コードが散乱しており、足元への注意が必要です。",
                observations=[
                    "床面に複数の日用品およびコードが露出している",
                    "室内照明は点灯しているが足元の見通しが悪い"
                ],
                hazards=[
                    HazardItem(
                        category="obstacle",
                        description="床に散乱した衣服および充電ケーブル",
                        location_hint="部屋中央フロア",
                        severity="medium"
                    )
                ],
                recommendations=[
                    "配線カバー等を用いてコード類を壁際に固定してください。"
                ]
            )
        elif hint_key == "unknown_simulated":
            analysis = RoomSafetyAnalysis(
                risk_level=SafetyRiskLevel.UNKNOWN,
                summary="光量不足または遮蔽物により、室内の安全状態を正確に確認できませんでした。",
                observations=["視界不良または逆光"],
                hazards=[],
                recommendations=["照明を点灯するか、カメラの向きを確認してください。"]
            )
        else:
            # Default normal room
            analysis = RoomSafetyAnalysis(
                risk_level=SafetyRiskLevel.LOW,
                summary="室内環境は整頓されており、明らかな転倒リスクや危険は見当たりません。",
                observations=[
                    "床面に障害物や散乱物は見当たらない",
                    "十分な照明が確保されている",
                    "歩行動線が十分に確保されている"
                ],
                hazards=[],
                recommendations=["現在の良好な室内環境を維持してください。"]
            )

        # Mock token usage & cost (gemini-3.8-flash pricing estimate: ~$0.10/1M input, $0.40/1M output)
        prompt_tokens = 280
        completion_tokens = 95
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = (prompt_tokens * 0.0000001) + (completion_tokens * 0.0000004)

        usage = GeminiUsageMetadata(
            model_id=f"{settings.GEMINI_MODEL_ID} (mock)",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost_usd, 7),
            is_mock=True
        )
        return analysis, usage

class RealGeminiService(GeminiServiceInterface):
    """
    Real Gemini Service using google-genai SDK.
    Strictly guarded by GEMINI_API_ENABLED and daily call limits to prevent unexpected billing.
    """
    def __init__(self, api_key: Optional[str] = None, model_id: Optional[str] = None):
        if not settings.GEMINI_API_ENABLED:
            raise GeminiDisabledError(
                "Gemini API is disabled by configuration (GEMINI_API_ENABLED=false). "
                "Explicit user activation and billing verification in Google AI Studio is required."
            )
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise GeminiDisabledError("GEMINI_API_KEY environment variable is not configured.")

        self.model_id = model_id or settings.GEMINI_MODEL_ID
        self.client = genai.Client(api_key=self.api_key)
        self.call_count = 0

    def analyze_room_safety(
        self,
        image_bytes: bytes,
        image_format: str,
        hint_key: Optional[str] = None
    ) -> Tuple[RoomSafetyAnalysis, GeminiUsageMetadata]:
        # Enforce quota protection
        if self.call_count >= settings.GEMINI_MAX_DAILY_CALLS:
            raise GeminiQuotaExceededError(
                f"Maximum daily call limit ({settings.GEMINI_MAX_DAILY_CALLS}) reached to prevent billing."
            )

        mime_type = f"image/{image_format.lower()}"
        if image_format.lower() == "jpg":
            mime_type = "image/jpeg"

        system_prompt = (
            "あなたは高齢者・在宅見守り支援のための室内安全診断AIアシスタントです。"
            "提供された室内画像から、転倒リスク・床の散らかり・危険な配線・姿勢異常などの危険候補を客観的に観察し、"
            "指定されたJSONスキーマに従って日本語で構造化出力してください。"
            "断定的な緊急通報判定は行わず、生活環境のリスク評価にとどめてください。"
            "画像が不鮮明な場合は risk_level='unknown' としてください。"
        )

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        user_prompt = "この室内画像を解析し、安全評価を行ってください。"

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=RoomSafetyAnalysis.model_json_schema(),
            temperature=0.2,
        )

        try:
            self.call_count += 1
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[user_prompt, image_part],
                config=config
            )
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                raise GeminiRateLimitError(f"Gemini API rate limit or quota exceeded: {e}")
            elif "500" in err_str or "503" in err_str or "internal" in err_str:
                raise GeminiServerError(f"Gemini API server error: {e}")
            else:
                raise GeminiError(f"Gemini API request failed: {e}")

        # Validate response content and structure
        if not response.text:
            raise GeminiResponseInvalidError("Empty response text from Gemini API")

        try:
            parsed_json = json.loads(response.text)
            analysis = RoomSafetyAnalysis.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as e:
            raise GeminiResponseInvalidError(f"Failed to parse Gemini response into RoomSafetyAnalysis schema: {e}")

        # Extract usage metadata
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0
            total_tokens = response.usage_metadata.total_token_count or (prompt_tokens + completion_tokens)

        cost_usd = (prompt_tokens * 0.0000001) + (completion_tokens * 0.0000004)
        usage = GeminiUsageMetadata(
            model_id=self.model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost_usd, 7),
            is_mock=False
        )
        return analysis, usage

# Factory providing Mock or Real service based strictly on configuration
def get_gemini_service() -> GeminiServiceInterface:
    if settings.GEMINI_API_ENABLED:
        logger.warning("[GeminiService] Real Gemini API is ENABLED. Network calls may incur billing.")
        return RealGeminiService()
    else:
        return MockGeminiService()
