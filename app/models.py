"""Pydantic models for the API request and response bodies."""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

# --- React가 기대하는 새로운 모델 ---

class WeatherRecommendationRequest(BaseModel):
    """React에서 보낼 요청 본문 (city, start_date, end_date)"""
    city: str = Field(..., description="날씨를 조회할 도시 이름 (예: 인천광역시)")
    start_date: str = Field(..., description="여행 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="여행 종료일 (YYYY-MM-DD)")

class SimpleWeatherInfo(BaseModel):
    """React가 날씨 목록에서 사용할 일일 날씨 요약"""
    date: str
    description: str
    temp_min: float
    temp_max: float
    feels_like: float

class WeatherRecommendationResponse(BaseModel):
    """React로 보낼 최종 응답 (일별 날씨 목록 + 종합 추천)"""
    weather: List[SimpleWeatherInfo] = Field(..., description="일자별 날씨 요약 목록")
    recommendation: str = Field(..., description="Gemini AI의 종합 옷차림 추천")


# --- 기존 모델 (다른 곳에서 사용할 수 있으므로 유지) ---

class WeatherSummary(BaseModel):
    temp: float
    feels_like: float
    temp_min: float
    temp_max: float
    humidity: int
    description: str
    wind_speed: float

class HourlyForecast(BaseModel):
    time: str
    temp: float
    description: str

class DailyRecommendation(BaseModel):
    date: str
    day_of_week: str
    destination: str
    weather_summary: Optional[WeatherSummary] = None
    hourly_forecasts: List[HourlyForecast] = []
    recommendation: str
    error: Optional[str] = None

class TravelRequest(BaseModel):
    destination: str
    travel_date: str
    duration: int

class TravelResponse(BaseModel):
    original_request: TravelRequest
    recommendations: List[DailyRecommendation]
