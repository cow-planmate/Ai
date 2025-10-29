"""Weather-related helpers using the OpenWeatherMap API."""

from datetime import datetime
from typing import Any, Dict, List

import requests

from app.config import settings


def translate_city_name(city_input: str) -> str:
    """Convert Korean city names to English equivalents where available."""
    city_dict = {
        # 국내
        "서울": "Seoul",
        "부산": "Busan",
        "인천": "Incheon",
        "대구": "Daegu",
        "대전": "Daejeon",
        "광주": "Gwangju",
        "울산": "Ulsan",
        "제주": "Jeju",
        # 해외
        "도쿄": "Tokyo",
        "오사카": "Osaka",
        "교토": "Kyoto",
        "후쿠오카": "Fukuoka",
        "삿포로": "Sapporo",
        "베이징": "Beijing",
        "상하이": "Shanghai",
        "홍콩": "Hong Kong",
        "타이베이": "Taipei",
        "방콕": "Bangkok",
        "싱가포르": "Singapore",
        "하노이": "Hanoi",
        "호치민": "Ho Chi Minh City",
        "뉴욕": "New York",
        "로스앤젤레스": "Los Angeles",
        "런던": "London",
        "파리": "Paris",
        "로마": "Rome",
        "바르셀로나": "Barcelona",
        "시드니": "Sydney",
        "멜버른": "Melbourne",
    }
    return city_dict.get(city_input, city_input)


def get_weather_forecast(city: str, target_date: datetime) -> Dict[str, Any]:
    """Fetch OpenWeatherMap forecast data for the given city and date."""
    days_diff = (target_date.date() - datetime.now().date()).days

    if days_diff < 0:
        return {"error": "과거 날짜의 날씨는 조회할 수 없습니다."}

    if days_diff > 4:
        return {"error": "무료 API는 5일 이내 예보만 제공합니다.", "alternative": True}

    if not settings.openweather_api_key:
        return {"error": "OPENWEATHER_API_KEY가 설정되지 않았습니다."}

    url = (
        f"http://api.openweathermap.org/data/2.5/forecast?q={city}"
        f"&appid={settings.openweather_api_key}&units=metric&lang=kr"
    )

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            target_date_str = target_date.strftime("%Y-%m-%d")
            daily_forecasts: List[Dict[str, Any]] = []

            for item in data.get("list", []):
                forecast_time = datetime.fromtimestamp(item["dt"])
                if forecast_time.strftime("%Y-%m-%d") == target_date_str:
                    daily_forecasts.append(
                        {
                            "time": forecast_time.strftime("%H:%M"),
                            "temp": round(item["main"]["temp"]),
                            "feels_like": round(item["main"]["feels_like"]),
                            "description": item["weather"][0]["description"],
                            "humidity": item["main"]["humidity"],
                            "wind_speed": item.get("wind", {}).get("speed", 0),
                        }
                    )

            if daily_forecasts:
                avg_temp = round(sum(f["temp"] for f in daily_forecasts) / len(daily_forecasts))
                avg_feels_like = round(
                    sum(f["feels_like"] for f in daily_forecasts) / len(daily_forecasts)
                )
                avg_humidity = round(sum(f["humidity"] for f in daily_forecasts) / len(daily_forecasts))
                descriptions = [f["description"] for f in daily_forecasts]
                main_description = max(set(descriptions), key=descriptions.count)

                return {
                    "forecasts": daily_forecasts,
                    "summary": {
                        "temp": avg_temp,
                        "feels_like": avg_feels_like,
                        "humidity": avg_humidity,
                        "description": main_description,
                        "wind_speed": daily_forecasts[0]["wind_speed"],
                    },
                }

            return {"error": "해당 날짜의 예보를 찾을 수 없습니다."}

        if response.status_code == 404:
            return {"error": f"도시를 찾을 수 없습니다: {city}"}

        return {"error": f"API 오류: {response.status_code}"}
    except Exception as exc:  # pragma: no cover - external API call
        return {"error": f"날씨 정보 가져오기 실패: {exc}"}

