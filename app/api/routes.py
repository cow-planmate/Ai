"""Route definitions for the travel outfit recommendation API."""

import re
import traceback  # [수정] 상세 오류 로깅을 위해 traceback 임포트
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil import parser
from fastapi import APIRouter, HTTPException

from app.models import (
    WeatherRecommendationRequest,  # [수정] 새로운 요청 모델
    WeatherRecommendationResponse, # [수정] 새로운 응답 모델
    SimpleWeatherInfo,             # [수정] 새로운 날씨 요약 모델
    WeatherSummary,                # (유지)
    DailyRecommendation,           # (유지)
    TravelRequest,                 # (유지)
    TravelResponse,                # (유지)
    HourlyForecast                 # (유지)
)
from app.services.recommendations import (
    recommend_outfit_gemini,
    recommend_outfit_rule_based,
)
from app.services.weather import get_weather_forecast, translate_city_name

router = APIRouter()


# [수정] React의 요청/응답에 맞게 엔드포인트 전체 로직을 수정합니다.
@router.post("/recommendations", response_model=WeatherRecommendationResponse)
def get_weather_recommendations(
    request: WeatherRecommendationRequest,
) -> WeatherRecommendationResponse:
    """
    여행 도시, 시작일, 종료일을 받아 일자별 날씨와
    종합 옷차림 추천을 JSON으로 반환합니다.
    """
    # --- [500 오류 수정] ---
    # 함수 전체를 try...except로 감싸서 모든 오류를 로깅합니다.
    try:
        try:
            start_date = datetime.fromisoformat(request.start_date)
            end_date = datetime.fromisoformat(request.end_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 날짜 형식입니다: {exc}. 'YYYY-MM-DD' 형식을 사용해야 합니다.",
            )

        # 날짜 차이 계산
        duration = (end_date - start_date).days + 1
        if duration <= 0 or duration > 16: # OpenWeather 16일 예보 제한
                raise HTTPException(
                status_code=400,
                detail=f"여행 기간은 1일에서 16일 사이여야 합니다. (요청: {duration}일)",
            )

        destination = translate_city_name(request.city)
        
        daily_weather_list: List[SimpleWeatherInfo] = []
        full_weather_prompt = (
            f"여행지: {destination}\n"
            f"여행 기간: {request.start_date} ~ {request.end_date}\n"
            "날씨 예보:\n"
        )
        
        for offset in range(duration):
            target_date = start_date + timedelta(days=offset)
            date_str_formatted = target_date.strftime("%Y-%m-%d")

            # 날씨 데이터 가져오기 (기존 서비스 재사용)
            weather_data = get_weather_forecast(destination, target_date)
            
            weather_summary_data: Optional[Dict[str, Any]] = None

            if "error" in weather_data:
                # 날씨 API 실패 시, 계절별 기본값으로 대체 (기존 로직)
                if weather_data.get("alternative"):
                    month = target_date.month
                    if month in [6, 7, 8]: temp, desc = 28, "더운 여름 날씨"
                    elif month in [3, 4, 5]: temp, desc = 18, "따뜻한 봄 날씨"
                    elif month in [9, 10, 11]: temp, desc = 15, "선선한 가을 날씨"
                    else: temp, desc = 5, "추운 겨울 날씨"
                    
                    weather_summary_data = {
                        "temp": temp, "feels_like": temp, "temp_min": temp,
                        "temp_max": temp, "humidity": 60, "description": desc, "wind_speed": 2,
                    }
                else:
                    # 대체도 불가능하면 에러 발생
                    raise HTTPException(
                        status_code=500,
                        detail=f"{date_str_formatted} 날씨 정보를 가져올 수 없습니다: {weather_data['error']}",
                    )
            else:
                weather_summary_data = weather_data.get("summary")

            if not weather_summary_data:
                    raise HTTPException(
                        status_code=500,
                        detail=f"{date_str_formatted} 날씨 요약 정보가 없습니다.",
                    )
            
            # [방어 코드 1] (원본 유지)
            avg_temp = weather_summary_data.get("temp", 15.0) 
            simple_weather = SimpleWeatherInfo(
                date=date_str_formatted,
                description=weather_summary_data.get("description", "날씨 정보 없음"),
                temp_min=weather_summary_data.get("temp_min", avg_temp - 3),
                temp_max=weather_summary_data.get("temp_max", avg_temp + 3),
                feels_like=weather_summary_data.get("feels_like", avg_temp),
            )
            
            daily_weather_list.append(simple_weather)
            
            # Gemini에게 보낼 전체 프롬프트 문자열 구성
            full_weather_prompt += (
                f"- {date_str_formatted}: {simple_weather.description}, "
                f"기온 {simple_weather.temp_min:.1f}°C ~ {simple_weather.temp_max:.1f}°C, "
                f"체감 {simple_weather.feels_like:.1f}°C\n"
            )

        # [방어 코드 2] (원본 유지)
        try:
            # Gemini 호출
            final_recommendation = recommend_outfit_gemini(
                full_weather_prompt, 
                destination,
                f"{request.start_date} ~ {request.end_date}",
            )

            # Gemini 실패 시 규칙 기반 대체
            if not final_recommendation:
                first_day_weather = daily_weather_list[0]
                fallback_summary = {
                    "temp": (first_day_weather.temp_min + first_day_weather.temp_max) / 2,
                    "description": first_day_weather.description,
                    "feels_like": first_day_weather.feels_like,
                    "humidity": 60, 
                    "wind_speed": 2,
                }
                final_recommendation = recommend_outfit_rule_based(fallback_summary)

        except Exception as e:
            print(f"!!! AI 추천 생성 중 오류 발생: {e}")
            
            # 2차 Fallback (규칙 기반) 시도
            try:
                if daily_weather_list:
                    first_day_weather = daily_weather_list[0]
                    fallback_summary = {
                        "temp": (first_day_weather.temp_min + first_day_weather.temp_max) / 2,
                        "description": first_day_weather.description,
                        "feels_like": first_day_weather.feels_like,
                        "humidity": 60, 
                        "wind_speed": 2, 
                    }
                    final_recommendation = recommend_outfit_rule_based(fallback_summary)
                else:
                    final_recommendation = None
            except Exception as e2:
                print(f"!!! 2차 Fallback 로직 실패: {e2}")
                final_recommendation = None

            if not final_recommendation:
                 final_recommendation = "날씨 정보가 복잡하여 AI 추천 생성에 실패했습니다. 기본 옷차림을 준비해주세요."


        return WeatherRecommendationResponse(
            weather=daily_weather_list,
            recommendation=final_recommendation or "옷차림 추천을 생성하지 못했습니다.",
        )
        
    # --- [500 오류 수정] ---
    # Pydantic 유효성 검사 오류, KeyError, TypeError 등 모든 오류를 여기서 잡습니다.
    except Exception as e:
        # Anaconda 프롬프트에 자세한 오류 로그를 출력합니다.
        print("\n" + "="*50)
        print(f"!!! FATAL ERROR in /recommendations: {e}")
        traceback.print_exc() # <--- 이것이 결정적인 로그입니다.
        print("="*50 + "\n")
        
        # 사용자(React)에게는 500 오류를 반환합니다.
        raise HTTPException(
            status_code=500,
            detail=f"서버 내부 오류 발생: {e}",
        )
    # --- [수정 완료] ---


# [참고] 기존 엔드포인트입니다. 새 엔드포인트가 정상 작동하면 이 코드는 삭제해도 됩니다.
@router.post("/recommendations_old", response_model=TravelResponse, include_in_schema=False)
def get_recommendations_old(request: TravelRequest) -> TravelResponse:
    """[구 버전] 여행 정보를 받아 날씨 예보와 옷차림 추천을 JSON으로 반환합니다."""
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
                    # [버그 가능성] 기존 "alternative" 딕셔너리에 temp_min, temp_max가 없었습니다.
                    "temp_min": temp_estimate - 2,
                    "temp_max": temp_estimate + 2,
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
                weather_summary_for_reco, # 이 부분은 새 로직과 다름 (Dict 전달)
                destination,
                date_str_formatted,
            )

        if not recommendation_text and weather_summary_for_reco:
            recommendation_text = recommend_outfit_rule_based(weather_summary_for_reco)

        daily_result.recommendation = recommendation_text or "추천 생성에 실패했습니다."
        results_list.append(daily_result)

    return TravelResponse(original_request=request, recommendations=results_list)

