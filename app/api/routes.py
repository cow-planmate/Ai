"""Route definitions for the travel outfit recommendation API."""

from fastapi import APIRouter
from app.services.recommendation_service import generate_recommendations 
from app.services.chatbot_service import handle_java_chatbot_request
from app.models import (
    WeatherRecommendationRequest,
    WeatherRecommendationResponse,
    ChatBotActionResponse,
)
from typing import Optional
from pydantic import BaseModel, Field

router = APIRouter()


# 1. 옷차림 추천 
@router.post("/recommendations", response_model=WeatherRecommendationResponse)
def get_weather_recommendations(
    request: WeatherRecommendationRequest,
) -> WeatherRecommendationResponse:
    """
    여행 도시, 시작일, 종료일을 받아 일자별 날씨와
    종합 옷차림 추천을 JSON으로 반환합니다.
    """
    # 핵심: 비즈니스 로직을 서비스 레이어(generate_recommendations)로 위임
    return generate_recommendations(request)


# 2. 챗봇 엔드포인트 (ChatRequest 모델을 여기에 정의)
class JavaChatbotRequest(BaseModel):
    planId: int = Field(..., description="여행 계획 ID")
    message: str = Field(..., description="사용자 메시지")
    systemPromptContext: str = Field(..., description="Java에서 생성한 시스템 프롬프트 컨텍스트 (계획 데이터 포함)")
    planContext: str = Field(..., description="Java에서 생성한 계획 컨텍스트 (계획 데이터 요약)")
    
@router.post("/api/chatbot/generate", response_model=ChatBotActionResponse)
def chat_generate_action(request: JavaChatbotRequest) -> ChatBotActionResponse:
    """
    Java 서버로부터 컨텍스트와 메시지를 받아 Gemini를 호출하고,
    처리된 ChatBotActionResponse를 Java에 반환합니다.
    """
    return handle_java_chatbot_request(
        request.planId,
        request.message,
        request.systemPromptContext,
        request.planContext
    )
