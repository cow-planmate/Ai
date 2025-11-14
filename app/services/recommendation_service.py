from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import traceback
import logging
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

# Logger for debug output (use uvicorn.error so it appears in the server logs)
logger = logging.getLogger("uvicorn.error")

def generate_recommendations(
    request: WeatherRecommendationRequest,
) -> WeatherRecommendationResponse:
    """
    여행 도시, 시작일, 종료일을 받아 일자별 날씨와
    종합 옷차림 추천을 JSON으로 반환합니다. (routes.py에서 분리된 비즈니스 로직)
    """
    try:
        # DEBUG: 요청 내용 로깅
        try:
            logger.debug("DEBUG: generate_recommendations request: %s", request.dict())
        except Exception:
            # 안전하게 request를 문자열로 출력
            logger.debug("DEBUG: generate_recommendations request (repr): %r", request)

        try:
            start_date = datetime.fromisoformat(request.start_date)
            end_date = datetime.fromisoformat(request.end_date)
        except ValueError as exc:
            logger.debug("Invalid date format: %s", exc)
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

        logger.debug("Translating city name: %s", request.city)
        destination = translate_city_name(request.city)
        logger.debug("Translated destination: %s", destination)
        
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
            logger.debug("Weather data for %s on %s: %s", destination, date_str_formatted, weather_data)
            weather_summary_data: Optional[Dict[str, Any]] = None

            if "error" in weather_data:
                # 과거 날짜 또는 대체값 지시가 있는 경우 시즌 평균으로 대체
                error_msg = str(weather_data.get("error", ""))
                if weather_data.get("alternative") or "과거" in error_msg or "past" in error_msg.lower():
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
                    # 기타 오류는 클라이언트에게 명확히 알립니다.
                    logger.debug("Weather API error for %s: %s", date_str_formatted, error_msg)
                    raise HTTPException(
                        status_code=500,
                        detail=f"{date_str_formatted} 날씨 정보를 가져올 수 없습니다: {error_msg}",
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
            logger.debug("Calling Gemini recommend_outfit_gemini (prompt length=%d)", len(full_weather_prompt))
            final_recommendation = recommend_outfit_gemini(
                full_weather_prompt,
                destination,
                f"{request.start_date} ~ {request.end_date}",
            )
            logger.debug("Gemini returned (truncated): %s", (final_recommendation[:500] if final_recommendation else None))

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
            logger.exception("!!! AI 추천 생성 중 오류 발생: %s", e)
            
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
                    logger.debug("Calling rule-based fallback with summary: %s", fallback_summary)
                    final_recommendation = recommend_outfit_rule_based(fallback_summary)
                else:
                    final_recommendation = None
            except Exception as e2:
                logger.exception("!!! 2차 Fallback 로직 실패: %s", e2)
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
        # 기타 500 오류 처리 - 상세 로그 출력
        logger.exception("!!! FATAL ERROR in generate_recommendations: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"서버 내부 오류 발생: {e}",
        )