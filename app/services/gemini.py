"""Gemini model initialisation and utilities."""

from typing import Any, Optional

from app.config import settings

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None


def init_gemini_model() -> Optional[Any]:
    """Configure Gemini SDK and return the first available model."""
    if not settings.gemini_api_key:
        print("ℹ️ Gemini API 키가 설정되지 않았습니다. 규칙 기반 추천만 사용합니다.")
        return None

    if genai is None:
        print("⚠️ google-generativeai 패키지를 찾을 수 없습니다. pip install google-generativeai 필요.")
        return None

    try:
        genai.configure(api_key=settings.gemini_api_key)
        available_models = [
            m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods
        ]
        for candidate in (
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash",
            "models/gemini-flash-latest",
        ):
            if candidate in available_models:
                model_id = candidate.replace("models/", "")
                print(f"✅ Gemini 모델 사용: {model_id}")
                return genai.GenerativeModel(model_id)

        print("⚠️ 사용 가능한 Gemini 모델이 없습니다. 규칙 기반 추천만 사용합니다.")
        return None
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"⚠️ Gemini 설정 오류: {exc}")
        return None


gemini_model = init_gemini_model()

