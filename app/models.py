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


from typing import List, Optional
from pydantic import BaseModel, Field

# --- 입력 모델 (Input) ---

class PlaceBlockVO(BaseModel):
    """장소 블록 정보 (프론트에서 넘어오는 원본 데이터 구조)"""
    blockId: int
    timeTableId: int
    placeCategory: int  # 0:관광, 1:숙소, 2:식당
    placeName: str
    placeAddress: str
    placeRating: float = 0.0
    # 필요한 필드만 정의 (나머지는 생략 가능하거나 Optional 처리)
    placeTheme: Optional[str] = None
    placeLink: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None

class TimetableVO(BaseModel):
    """타임테이블 정보 (날짜 매핑용)"""
    timetableId: int
    date: str  # YYYY-MM-DD
    startTime: Optional[str] = None
    endTime: Optional[str] = None

class PricePredictionRequest(BaseModel):
    headcount: int = Field(..., description="여행 인원 수")
    placeBlocks: List[PlaceBlockVO] = Field(..., description="장소 블록 리스트")
    timeTables: List[TimetableVO] = Field(..., description="타임테이블 리스트 (날짜 정보)")

# --- 출력 모델 (Output) ---

class CostRange(BaseModel):
    min: int
    max: int

class FoodCostDetail(BaseModel):
    placeName: str
    pricePerPerson: int
    totalPrice: int
    menuExamples: List[str] = []

class AccommodationCostDetail(BaseModel):
    placeName: str
    roomType: str
    priceRange: CostRange
    pricePerPerson: CostRange

# 날짜별 요약
class DailyCostSummary(BaseModel):
    date: str  # "2025-11-22"
    dayNumber: int # 1일차, 2일차...
    foodDetails: List[FoodCostDetail]
    accommodationDetails: List[AccommodationCostDetail]
    
    # 해당 날짜의 합계
    dailyTotalFood: int
    dailyTotalAccommodationMin: int
    dailyTotalAccommodationMax: int
    dailyTotalMin: int
    dailyTotalMax: int

# 전체 여행 요약
class TripTotalSummary(BaseModel):
    totalFoodCost: int
    totalAccommodationMin: int
    totalAccommodationMax: int
    
    # 1인당 예상 경비
    perPersonCost: CostRange
    # 전체 그룹 예상 경비
    groupTotalCost: CostRange

class PricePredictionResponse(BaseModel):
    dailyCosts: List[DailyCostSummary]
    tripSummary: TripTotalSummary