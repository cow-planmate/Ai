from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import traceback
from fastapi import HTTPException

from app.models import (
    WeatherRecommendationRequest,
    WeatherRecommendationResponse,
    SimpleWeatherInfo,
    WeatherSummary,
)
from app.services.recommendations import (
    recommend_outfit_gemini,
    recommend_outfit_rule_based,
)
from app.services.weather import get_weather_forecast, translate_city_name

def generate_recommendations(
    request: WeatherRecommendationRequest,
) -> WeatherRecommendationResponse:
    """
    여행 도시, 시작일, 종료일을 받아 일자별 날씨와
    종합 옷차림 추천을 JSON으로 반환합니다. (routes.py에서 분리된 비즈니스 로직)
    """
    try:
        try:
            start_date = datetime.fromisoformat(request.start_date)
            end_date = datetime.fromisoformat(request.end_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 날짜 형식입니다: {exc}. 'YYYY-MM-DD' 형식을 사용해야 합니다.",
            )

        duration = (end_date - start_date).days + 1
        if duration <= 0 or duration > 16:
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

            weather_data = get_weather_forecast(destination, target_date)
            weather_summary_data: Optional[Dict[str, Any]] = None

            if "error" in weather_data:
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
            
            avg_temp = weather_summary_data.get("temp", 15.0) 
            simple_weather = SimpleWeatherInfo(
                date=date_str_formatted,
                description=weather_summary_data.get("description", "날씨 정보 없음"),
                temp_min=weather_summary_data.get("temp_min", avg_temp - 3),
                temp_max=weather_summary_data.get("temp_max", avg_temp + 3),
                feels_like=weather_summary_data.get("feels_like", avg_temp),
            )
            
            daily_weather_list.append(simple_weather)
            
            full_weather_prompt += (
                f"- {date_str_formatted}: {simple_weather.description}, "
                f"기온 {simple_weather.temp_min:.1f}°C ~ {simple_weather.temp_max:.1f}°C, "
                f"체감 {simple_weather.feels_like:.1f}°C\n"
            )

        final_recommendation: Optional[str] = None
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
        
    except HTTPException:
        # 400 오류는 그대로 다시 발생시킵니다.
        raise
    except Exception as e:
        # 기타 500 오류 처리
        print("\n" + "="*50)
        print(f"!!! FATAL ERROR in generate_recommendations: {e}")
        traceback.print_exc()
        print("="*50 + "\n")
        
        raise HTTPException(
            status_code=500,
            detail=f"서버 내부 오류 발생: {e}",
        )