"""Route definitions for the travel outfit recommendation API."""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil import parser
from fastapi import APIRouter, HTTPException

from app.models import (
    DailyRecommendation,
    HourlyForecast,
    TravelRequest,
    TravelResponse,
    WeatherSummary,
)
from app.services.recommendations import (
    recommend_outfit_gemini,
    recommend_outfit_rule_based,
)
from app.services.weather import get_weather_forecast, translate_city_name

router = APIRouter()


@router.post("/recommendations", response_model=TravelResponse)
def get_recommendations(request: TravelRequest) -> TravelResponse:
    """여행 정보를 받아 날씨 예보와 옷차림 추천을 JSON으로 반환합니다."""
    destination_input = request.destination
    destination = translate_city_name(destination_input)
    travel_date_str = request.travel_date
    duration = request.duration

    try:
        if "월" in travel_date_str and "일" in travel_date_str:
            match = re.search(r"(\d+)월\s*(\d+)일", travel_date_str)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                year = datetime.now().year
                if datetime.now().month > month:
                    year += 1
                start_date = datetime(year, month, day)
            else:
                start_date = parser.parse(travel_date_str)
        else:
            start_date = parser.parse(travel_date_str)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"잘못된 날짜 형식입니다: {travel_date_str}. (오류: {exc})",
        ) from exc

    results_list: List[DailyRecommendation] = []

    for offset in range(duration):
        target_date = start_date + timedelta(days=offset)
        date_str_formatted = target_date.strftime("%Y년 %m월 %d일")
        day_of_week = target_date.strftime("%A")

        daily_result = DailyRecommendation(
            date=date_str_formatted,
            day_of_week=day_of_week,
            destination=destination_input,
            recommendation="",
        )

        weather_data = get_weather_forecast(destination, target_date)
        weather_summary_for_reco: Optional[Dict[str, Any]] = None

        if "error" in weather_data:
            daily_result.error = weather_data["error"]

            if weather_data.get("alternative"):
                month = target_date.month
                if month in [6, 7, 8]:
                    temp_estimate, desc_estimate = 28, "여름 날씨"
                elif month in [3, 4, 5]:
                    temp_estimate, desc_estimate = 18, "봄 날씨"
                elif month in [9, 10, 11]:
                    temp_estimate, desc_estimate = 15, "가을 날씨"
                else:
                    temp_estimate, desc_estimate = 5, "겨울 날씨"

                weather_summary_for_reco = {
                    "temp": temp_estimate,
                    "feels_like": temp_estimate,
                    "humidity": 60,
                    "description": desc_estimate,
                    "wind_speed": 2,
                }
                daily_result.weather_summary = WeatherSummary(**weather_summary_for_reco)
            else:
                daily_result.recommendation = "날씨 정보를 가져올 수 없어 추천이 불가능합니다."
                results_list.append(daily_result)
                continue

        else:
            weather_summary_for_reco = weather_data["summary"]
            daily_result.weather_summary = WeatherSummary(**weather_summary_for_reco)
            if "forecasts" in weather_data:
                daily_result.hourly_forecasts = [
                    HourlyForecast(
                        time=forecast["time"],
                        temp=forecast["temp"],
                        description=forecast["description"],
                    )
                    for forecast in weather_data["forecasts"]
                ]

        recommendation_text: Optional[str] = None
        if weather_summary_for_reco:
            recommendation_text = recommend_outfit_gemini(
                weather_summary_for_reco,
                destination,
                date_str_formatted,
            )

        if not recommendation_text and weather_summary_for_reco:
            recommendation_text = recommend_outfit_rule_based(weather_summary_for_reco)

        daily_result.recommendation = recommendation_text or "추천 생성에 실패했습니다."
        results_list.append(daily_result)

    return TravelResponse(original_request=request, recommendations=results_list)

