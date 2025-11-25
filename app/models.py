"""Pydantic models for the API request and response bodies."""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import date, time

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


class TimetablePlaceBlockVO(BaseModel):
    # Java의 VO와 필드 순서 및 타입 일치 (JSON 파싱을 위해 Optional 사용)
    timetableId: Optional[int] = None
    timetablePlaceBlockId: Optional[int] = None
    placeCategoryId: Optional[int] = None
    placeName: Optional[str] = None
    placeRating: Optional[float] = None
    placeAddress: Optional[str] = None
    placeLink: Optional[str] = None
    placeId: Optional[str] = None
    date: Optional[str] = None # Java에서는 LocalDate였으나, DTO에서는 문자열로 처리될 수 있음
    startTime: Optional[time] = None
    endTime: Optional[time] = None
    xLocation: Optional[float] = None
    yLocation: Optional[float] = None
    
class TimetableVO(BaseModel):
    timetableId: Optional[int] = None
    date: Optional[date] = None
    startTime: Optional[time] = None
    endTime: Optional[time] = None
    # timeTablePlaceBlocks: List[TimetablePlaceBlockVO] = [] # (선택적)

# --- Java AI 응답 모델 대체 (ChatBotActionResponse/AIResponse/ActionData) ---
class ChatBotRequest(BaseModel):
    planId: int
    message: str
    systemPromptContext: str
    planContext: dict[str, Any]

class ActionData(BaseModel):
    action: str               # create | update | delete
    targetName: str           # plan | timeTable | timeTablePlaceBlock
    target: Dict[str, Any]

class ChatBotActionResponse(BaseModel):
    userMessage: str
    hasAction: bool
    actions: List[ActionData] = Field(default_factory=list)

class AIResponse(BaseModel):
    """Gemini가 반환해야 하는 최종 JSON 구조"""
    userMessage: str
    hasAction: bool
    actions: List[ActionData] = Field(default_factory=list)
