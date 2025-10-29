"""Entrypoint helpers for the travel outfit recommendation API."""

import os
import threading
import time

import uvicorn

from app import app


def run_server() -> None:
    """Run the FastAPI application with uvicorn."""
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


def run_in_thread() -> None:
    """Start the server in a background thread (useful for notebooks)."""
    print("FastAPI 서버를 백그라운드 스레드에서 시작합니다...")
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(3)
    print("=" * 50)
    print("✅ FastAPI 서버가 성공적으로 실행되었습니다.")
    print("🌍 로컬 접속 URL: http://localhost:8000")
    print("📚 API 문서 (Swagger UI): http://localhost:8000/docs")
    print("📬 POST 엔드포인트: http://localhost:8000/recommendations")
    print("=" * 50)


if __name__ == "__main__":
    run_server()

