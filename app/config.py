"""Centralised configuration for environment-based settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if load_dotenv is not None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
elif ENV_PATH.exists():  # pragma: no cover - guidance for missing dependency
    print("⚠️ python-dotenv 패키지가 필요합니다. pip install python-dotenv 후 .env 파일을 로드하세요.")


@dataclass
class Settings:
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "").strip()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_api_url: str = os.getenv("GEMINI_API_URL", "").strip() 
    
    allowed_origins: List[str] = field(
        default_factory=lambda: [
            "https://www.planmate.site",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )


settings = Settings()