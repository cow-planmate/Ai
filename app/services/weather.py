"""Weather-related helpers using the OpenWeatherMap API."""

from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from app.config import settings


def translate_city_name(city_input: str) -> str:
    """
    "광주광역시 동구", "경기도 광주시", "강원특별자치도 화천군" 같은 입력을
    OpenWeatherMap이 인식하는 "Gwangju", "Gyeonggi-do", "Gangwon-do" 등으로 변환합니다.
    """
    
    # [수정] 사용자가 제공한 17개 광역 시/도 이미지 기준으로 city_dict를 재구성
    # 하위 도시(원주, 문경, 화천 등)를 모두 제거하고, 광역 단위만 매핑합니다. (무료 OpenweatherMap api를 사용해서 그렇습니다!)
    city_dict = {
        # 8개 특별/광역시
        "서울특별시": "Seoul",
        "부산광역시": "Busan",
        "대구광역시": "Daegu",
        "인천광역시": "Incheon",
        "광주광역시": "Gwangju",
        "대전광역시": "Daejeon",
        "울산광역시": "Ulsan",
        "세종특별자치시": "Sejong",
        
        # 9개 도
        "경기도": "Gyeonggi-do",
        "강원특별자치도": "Gangwon-do", # "강원"만 쓰면 "수원"과 혼동 가능
        "충청북도": "Chungcheongbuk-do",
        "충청남도": "Chungcheongnam-do",
        "전라북도": "Jeollabuk-do",
        "전라남도": "Jeollanam-do",
        "경상북도": "Gyeongsangbuk-do",
        "경상남도": "Gyeongsangnam-do",
        "제주특별자치도": "Jeju",
    }
    
    # [수정] 
    # 딕셔너리 키를 순회하며 입력 문자열에 포함되는지 확인합니다.
    # 이 로직은 `city_dict`가 상위 지역만 포함하므로 안전하게 작동합니다.
    for kor_city in city_dict:
        # "강원특별자치도"가 "강원특별자치도 화천군" 안에 포함되는지 확인 -> True
        if kor_city in city_input:
            # "Gangwon-do"를 반환
            return city_dict[kor_city]
            
    # 매칭되는 키가 없으면 원본 반환
    return city_input
    # --- [수정 완료] ---


def get_weather_forecast(city: str, target_date: datetime) -> Dict[str, Any]:
    """Fetch OpenWeatherMap forecast data for the given city and date."""
    days_diff = (target_date.date() - datetime.now().date()).days

    # If target date is in the past, optionally try the historical API
    if days_diff < 0:
        allow_hist = getattr(settings, "openweather_allow_historical", None)
        # Also accept env var style boolean string
        if allow_hist is None:
            import os

            allow_hist = os.getenv("OPENWEATHER_ALLOW_HISTORICAL", "false").lower() in ("1", "true", "yes")

        if allow_hist and settings.openweather_api_key:
            # Use Geocoding API to get lat/lon for the city
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={settings.openweather_api_key}"
            try:
                geo_resp = requests.get(geo_url, timeout=10)
                if geo_resp.status_code == 200 and geo_resp.json():
                    geo = geo_resp.json()[0]
                    lat = geo.get("lat")
                    lon = geo.get("lon")
                    if lat is None or lon is None:
                        return {"error": "Geocoding 실패: 위도/경도 정보를 찾을 수 없습니다."}

                    # One Call Time Machine endpoint requires a unix timestamp (UTC). Use midday UTC of the target date.
                    dt_ts = int(datetime(target_date.year, target_date.month, target_date.day, 12, tzinfo=timezone.utc).timestamp())
                    hist_url = (
                        f"https://api.openweathermap.org/data/2.5/onecall/timemachine?lat={lat}&lon={lon}&dt={dt_ts}"
                        f"&appid={settings.openweather_api_key}&units=metric&lang=kr"
                    )
                    hist_resp = requests.get(hist_url, timeout=10)
                    if hist_resp.status_code == 200:
                        data = hist_resp.json()
                        # hourly field contains hourly historical datapoints
                        hourly = data.get("hourly", [])
                        if not hourly:
                            return {"error": "히스토리컬 데이터가 없습니다.", "alternative": True}

                        daily_forecasts = []
                        for item in hourly:
                            forecast_time = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
                            daily_forecasts.append(
                                {
                                    "time": forecast_time.strftime("%H:%M"),
                                    "temp": round(item["temp"]),
                                    "feels_like": round(item.get("feels_like", item.get("temp", 0))),
                                    "description": item.get("weather", [{}])[0].get("description", ""),
                                    "humidity": item.get("humidity", 0),
                                    "wind_speed": item.get("wind_speed", 0),
                                    "temp_min": round(item.get("temp", 0)),
                                    "temp_max": round(item.get("temp", 0)),
                                }
                            )

                        if daily_forecasts:
                            avg_temp = round(sum(f["temp"] for f in daily_forecasts) / len(daily_forecasts))
                            avg_feels_like = round(
                                sum(f["feels_like"] for f in daily_forecasts) / len(daily_forecasts)
                            )
                            avg_humidity = round(sum(f["humidity"] for f in daily_forecasts) / len(daily_forecasts))

                            min_temp_of_day = min(f["temp_min"] for f in daily_forecasts)
                            max_temp_of_day = max(f["temp_max"] for f in daily_forecasts)

                            descriptions = [f["description"] for f in daily_forecasts]
                            main_description = max(set(descriptions), key=descriptions.count) if descriptions else ""

                            return {
                                "forecasts": daily_forecasts,
                                "summary": {
                                    "temp": avg_temp,
                                    "feels_like": avg_feels_like,
                                    "humidity": avg_humidity,
                                    "description": main_description,
                                    "wind_speed": daily_forecasts[0]["wind_speed"],
                                    "temp_min": min_temp_of_day,
                                    "temp_max": max_temp_of_day,
                                },
                            }
                    else:
                        # Historical endpoint may require paid plan or be unavailable
                        return {"error": f"Historical API 오류: {hist_resp.status_code}", "alternative": True}
                else:
                    return {"error": "Geocoding 실패: 도시 정보를 찾을 수 없습니다."}
            except Exception as exc:
                return {"error": f"히스토리컬 데이터 조회 실패: {exc}", "alternative": True}

        # Historical not allowed or key missing -> fall back to previous behavior (seasonal/alternative)
        return {"error": "과거 날짜의 날씨는 조회할 수 없습니다."}

    # 무료 플랜 5일 예보를 계속 사용
    if days_diff > 4:
        # 5일이 넘어가면 "alternative": True를 반환하여 routes.py가 계절별 날씨를 반환하도록 함
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
                            "temp_min": round(item["main"].get("temp_min", item["main"]["temp"])),
                            "temp_max": round(item["main"].get("temp_max", item["main"]["temp"])),
                        }
                    )

            if daily_forecasts:
                avg_temp = round(sum(f["temp"] for f in daily_forecasts) / len(daily_forecasts))
                avg_feels_like = round(
                    sum(f["feels_like"] for f in daily_forecasts) / len(daily_forecasts)
                )
                avg_humidity = round(sum(f["humidity"] for f in daily_forecasts) / len(daily_forecasts))
                
                min_temp_of_day = min(f["temp_min"] for f in daily_forecasts)
                max_temp_of_day = max(f["temp_max"] for f in daily_forecasts)

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
                        "temp_min": min_temp_of_day,
                        "temp_max": max_temp_of_day,
                    },
                }

            if days_diff <= 4:
                 return {"error": f"{target_date_str}의 예보 데이터를 찾을 수 없습니다 (API 응답은 정상).", "alternative": True}
            
            return {"error": "해당 날짜의 예보를 찾을 수 없습니다."}

        if response.status_code == 404:
            # "Gangwon-do"로 변환했는데도 404가 발생한 경우 (OpenWeatherMap이 모르는 도시)
            return {"error": f"도시를 찾을 수 없습니다: {city}"}

        return {"error": f"API 오류: {response.status_code}"}
    except Exception as exc:  # pragma: no cover - external API call
        return {"error": f"날씨 정보 가져오기 실패: {exc}"}

