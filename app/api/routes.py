"""Route definitions for the travel outfit recommendation API."""

from fastapi import APIRouter
from app.services.price_service import predict_price_service
from app.services.recommendation_service import generate_recommendations 
from app.services.chatbot_service import handle_java_chatbot_request
from app.models import (
    PricePredictionRequest,
    PricePredictionResponse,
    WeatherRecommendationRequest,
    WeatherRecommendationResponse,
    ChatBotActionResponse, ChatBotRequest,
)

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


# 2. 챗봇 엔드포인트
@router.post("/api/chatbot/generate", response_model=ChatBotActionResponse)
def chat_generate_action(request: ChatBotRequest) -> ChatBotActionResponse:
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

@router.post("/price", response_model=PricePredictionResponse)
def predict_price(request: PricePredictionRequest) -> PricePredictionResponse: 
    """
    주어진 입력 데이터(식당, 숙소, 인원수)를 기반으로 1인당 및 총 여행 경비를 예측합니다.
    """
    return predict_price_service(request)
