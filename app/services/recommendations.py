"""Outfit recommendation helpers."""

from typing import Any, Dict, Optional

from app.services.gemini import gemini_model


def recommend_outfit_gemini(weather_summary: Dict[str, Any], destination: str, date_str: str) -> Optional[str]:
    """Generate a recommendation using Gemini when available."""
    if gemini_model is None:
        return None

    prompt = f"""
당신은 여행 패션 전문가입니다. 다음 여행 정보를 바탕으로 적절한 옷차림을 추천해주세요.

📍 여행 정보:
- 목적지: {destination}
- 날짜: {date_str}
- 예상 날씨: {weather_summary['description']}
- 평균 기온: {weather_summary['temp']}°C (체감 {weather_summary['feels_like']}°C)
- 습도: {weather_summary['humidity']}%

다음 형식으로 답변해주세요:
1. 추천 옷차림 (상의, 하의, 겉옷)
2. 필수 준비물
3. 여행 팁

답변은 친근하고 실용적으로 작성해주세요.
"""
    try:
        response = gemini_model.generate_content(prompt)
        return getattr(response, "text", None)
    except Exception as exc:  # pragma: no cover - external API call
        print(f"Gemini API 오류: {exc}")
        return None


def recommend_outfit_rule_based(weather_summary: Dict[str, Any]) -> str:
    """Fallback rule-based recommendation."""
    temp = weather_summary["temp"]
    desc = weather_summary["description"]
    humidity = weather_summary["humidity"]

    recommendation = {"outfit": "", "items": [], "advice": ""}

    if temp >= 28:
        recommendation["outfit"] = "반팔 티셔츠와 반바지 또는 린넨 소재의 가벼운 옷"
        recommendation["items"] = ["선글라스", "모자", "선크림", "물병"]
        recommendation["advice"] = "매우 더운 날씨입니다. 수분 섭취에 유의하세요!"
    elif temp >= 23:
        recommendation["outfit"] = "반팔 티셔츠와 청바지, 면 소재 옷"
        recommendation["items"] = ["얇은 가디건", "선글라스", "모자"]
        recommendation["advice"] = "쾌적한 날씨입니다. 일교차에 대비해 얇은 겉옷을 준비하세요."
    elif temp >= 20:
        recommendation["outfit"] = "긴팔 티셔츠, 얇은 니트"
        recommendation["items"] = ["가벼운 재킷", "편한 신발"]
        recommendation["advice"] = "선선한 날씨입니다. 활동하기 좋은 온도예요!"
    elif temp >= 17:
        recommendation["outfit"] = "긴팔 셔츠에 가디건 또는 자켓"
        recommendation["items"] = ["스카프", "편한 운동화"]
        recommendation["advice"] = "약간 쌀쌀합니다. 겉옷을 꼭 챙기세요."
    elif temp >= 12:
        recommendation["outfit"] = "니트나 맨투맨에 자켓"
        recommendation["items"] = ["목도리", "바람막이"]
        recommendation["advice"] = "쌀쌀한 날씨입니다. 따뜻하게 입으세요."
    elif temp >= 5:
        recommendation["outfit"] = "두꺼운 코트와 기모 옷"
        recommendation["items"] = ["목도리", "장갑", "방한 모자"]
        recommendation["advice"] = "추운 날씨입니다. 방한 준비를 철저히 하세요."
    else:
        recommendation["outfit"] = "패딩과 방한 장비"
        recommendation["items"] = ["두꺼운 목도리", "방한 장갑", "방한 모자", "핫팩"]
        recommendation["advice"] = "매우 추운 날씨입니다. 여러 겹 레이어드로 입으세요!"

    if "비" in desc or "rain" in desc.lower():
        recommendation["items"].extend(["우산", "방수 재킷", "방수 신발"])
        recommendation["advice"] += " 비가 예상되니 우산과 방수 용품을 준비하세요."
    if "눈" in desc or "snow" in desc.lower():
        recommendation["items"].extend(["방수 부츠", "미끄럼 방지 신발"])
        recommendation["advice"] += " 눈이 예상되니 미끄럼 방지 신발을 신으세요."
    if humidity >= 80:
        recommendation["advice"] += " 습도가 높으니 통풍이 잘 되는 옷을 입으세요."

    return f"""
👔 추천 옷차림:
{recommendation['outfit']}

🎒 필수 준비물:
{', '.join(recommendation['items'])}

💡 여행 팁:
{recommendation['advice']}
""".strip()

