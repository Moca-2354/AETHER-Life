"""
AETHER Life v0.3 — Safe Single Gemini API Call Verification Script
This script is strictly intended for 1-time verification with safety guards.
It uses an artificial mock image (no humans/personal data) and enforces a hard limit of 1 call.
"""
import os
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.services.camera_service import MockCameraService
from app.services.gemini_service import RealGeminiService
from app.schemas.safety import RoomSafetyAnalysis

def run_single_test():
    print("=" * 60)
    print("AETHER Life — Gemini API Single Test Verification")
    print("=" * 60)

    # 1. Verify API Key existence without displaying it
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not configured in backend/.env")
        sys.exit(1)

    print(f"[OK] API Key recognized (Length: {len(api_key)}) — Value hidden.")
    print(f"[OK] Model ID to be tested: {settings.GEMINI_MODEL_ID}")

    # 2. Load safe mock image (no human/PII)
    camera = MockCameraService()
    try:
        capture_result = camera.capture("living_room_normal")
        print(f"[OK] Mock test image loaded: {capture_result.metadata.format.upper()} ({capture_result.metadata.width}x{capture_result.metadata.height}, {capture_result.metadata.size_bytes} bytes)")
        print(f"     File: tests/fixtures/mock_images/living_room_normal.jpg (Geometric dummy image)")
    except Exception as e:
        print(f"[ERROR] Failed loading mock image: {e}")
        sys.exit(1)

    # 3. Initialize RealGeminiService with safety limit
    # Temporarily instantiate RealGeminiService for this 1-time script only
    print("[INFO] Initializing RealGeminiService (Hard limit: exactly 1 call)...")
    try:
        # Override enabled check solely for this isolated runner
        orig_enabled = settings.GEMINI_API_ENABLED
        settings.GEMINI_API_ENABLED = True
        service = RealGeminiService(api_key=api_key, model_id=settings.GEMINI_MODEL_ID)
    except Exception as e:
        print(f"[ERROR] Failed initializing RealGeminiService: {e}")
        sys.exit(1)
    finally:
        # Immediately restore safety setting
        settings.GEMINI_API_ENABLED = orig_enabled

    # 4. Execute the single call
    print("[INFO] Sending single structured analysis request to Gemini API...")
    try:
        analysis, usage = service.analyze_room_safety(
            image_bytes=capture_result.image_bytes,
            image_format=capture_result.metadata.format,
            hint_key=None
        )
    except Exception as e:
        print(f"[FAILED] Gemini API call failed: {e}")
        sys.exit(1)

    # 5. Output structured result & cost metrics
    print("\n" + "-" * 40)
    print("Gemini API Call Succeeded!")
    print("-" * 40)
    print(f"Risk Level    : {analysis.risk_level.value}")
    print(f"Summary       : {analysis.summary}")
    print(f"Observations  : {analysis.observations}")
    print(f"Hazards       : {analysis.hazards}")
    print(f"Recommendations: {analysis.recommendations}")
    print("-" * 40)
    print("Usage & Estimated Billing:")
    print(f"Prompt Tokens     : {usage.prompt_tokens}")
    print(f"Completion Tokens : {usage.completion_tokens}")
    print(f"Total Tokens      : {usage.total_tokens}")
    print(f"Estimated Cost USD: ${usage.estimated_cost_usd:.7f}")
    print(f"Is Mock           : {usage.is_mock}")
    print("=" * 60)
    print("[SAFETY CHECK] Global GEMINI_API_ENABLED remains:", settings.GEMINI_API_ENABLED)
    print("Verification completed successfully.")

if __name__ == "__main__":
    run_single_test()
