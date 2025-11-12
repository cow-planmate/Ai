"""Application factory for the travel outfit recommendation API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="여행 날씨 기반 옷차림 추천 API",
        description="여행지, 날짜, 기간을 입력받아 날씨와 옷차림을 추천합니다.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # config.py의 allowed_origins 설정을 사용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://www.planmate.site"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()

