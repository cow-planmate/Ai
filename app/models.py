"""Pydantic models defining request and response schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class TravelRequest(BaseModel):
    destination: str = Field(..., description="여행 목적지 (한글 또는 영어)", example="서울")
    travel_date: str = Field(..., description="여행 시작 날짜", example="2025-10-29")
    duration: int = Field(default=1, ge=1, le=7, description="여행 기간 (일, 1일~7일)", example=3)


class WeatherSummary(BaseModel):
    temp: float
    feels_like: float
    humidity: float
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
    hourly_forecasts: List[HourlyForecast] = Field(default_factory=list)
    recommendation: str
    error: Optional[str] = None


class TravelResponse(BaseModel):
    original_request: TravelRequest
    recommendations: List[DailyRecommendation]

