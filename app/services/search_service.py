# app/services/search_service.py

from datetime import datetime, time, timedelta, date as date_type
from typing import List, Dict, Any, Tuple, Optional

import requests

from app.config import settings


DAY_START = time(9, 0, 0)
DAY_END = time(20, 0, 0)

# 자동 일정 생성 시간대 정의
AUTO_SCHEDULE_TIMES = {
    "morning": {"start": time(9, 0, 0), "end": time(10, 0, 0), "type": "맛집"},
    "lunch": {"start": time(12, 0, 0), "end": time(13, 0, 0), "type": "맛집"},
    "afternoon": {"start": time(14, 0, 0), "end": time(17, 0, 0), "type": "관광지"},
    "dinner": {"start": time(18, 0, 0), "end": time(19, 0, 0), "type": "맛집"},
    "accommodation": {"start": time(19, 0, 0), "end": time(20, 0, 0), "type": "숙소"},
}


def parse_blocks_from_plan(planContext: dict) -> List[Dict[str, Any]]:
    """
    planContext 에서 TimeTablePlaceBlocks 리스트만 뽑아온다.
    없으면 빈 리스트.
    """
    return planContext.get("TimeTablePlaceBlocks", []) or []


def get_destination_location(destination: str) -> Optional[str]:
    """
    목적지 이름으로 위치 좌표를 검색합니다.
    Google Geocoding API 또는 Places API를 사용하여 목적지의 중심 좌표를 가져옵니다.

    Args:
        destination: 목적지 이름 (예: "서울", "부산", "제주도")

    Returns:
        "latitude,longitude" 형식의 문자열 또는 None
    """
    if not destination:
        return None

    try:
        # Google Places API Text Search로 목적지 검색
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": destination,
            "key": settings.google_places_api_key,
            "language": "ko",
        }

        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        if data.get("status") == "OK" and data.get("results"):
            result = data["results"][0]
            lat = result["geometry"]["location"]["lat"]
            lng = result["geometry"]["location"]["lng"]
            print(f"[LOCATION] 목적지 '{destination}' 위치: {lat},{lng}")
            return f"{lat},{lng}"

    except Exception as e:
        print(f"[ERROR] 목적지 위치 검색 실패: {e}")

    return None


def get_location_from_plan(planContext: dict, timeTableId: int) -> Optional[str]:
    """
    planContext에서 해당 timeTableId의 기존 장소 블록 중 하나의 위치를 가져온다.
    같은 날짜(timeTableId)의 장소들이 여러 개 있을 경우 첫 번째 장소의 위치를 반환.
    없으면 전체 블록 중 첫 번째 장소의 위치를 반환.
    그마저도 없으면 TravelName(목적지)으로 위치를 검색합니다.

    Returns:
        "latitude,longitude" 형식의 문자열 또는 None
    """
    blocks = parse_blocks_from_plan(planContext)

    # 1. 같은 timeTableId의 블록 찾기
    if blocks:
        same_day_blocks = [b for b in blocks if b.get("timeTableId") == timeTableId]

        # 2. 같은 날짜의 블록이 있으면 그 중 첫 번째 위치 사용
        if same_day_blocks:
            for block in same_day_blocks:
                y_loc = block.get("yLocation")
                x_loc = block.get("xLocation")
                if y_loc is not None and x_loc is not None:
                    return f"{y_loc},{x_loc}"

        # 3. 같은 날짜의 블록이 없으면 전체 블록 중 첫 번째 위치 사용 (여행지 근처일 가능성 높음)
        for block in blocks:
            y_loc = block.get("yLocation")
            x_loc = block.get("xLocation")
            if y_loc is not None and x_loc is not None:
                return f"{y_loc},{x_loc}"

    # 4. 블록이 하나도 없으면 TravelName(목적지)으로 위치 검색
    travel_name = planContext.get("TravelName")
    if travel_name:
        print(f"[SEARCH] 기존 장소 블록이 없어서 목적지 '{travel_name}'로 위치 검색")
        return get_destination_location(travel_name)

    return None


def _parse_time(t) -> time:
    """
    다양한 시간 포맷을 파싱합니다.
    - "HH:MM:SS" (예: "09:00:00")
    - "HH:MM" (예: "09:00")
    - [HH, MM] (예: [10, 0]) - Jackson LocalTime 배열 형식
    - [HH, MM, SS] (예: [10, 0, 30])
    """
    if not t:
        raise ValueError("Time value is empty")

    # 배열/리스트 형식인 경우 (Jackson LocalTime 직렬화)
    if isinstance(t, list):
        if len(t) == 2:
            # [시, 분]
            return time(hour=t[0], minute=t[1], second=0)
        elif len(t) == 3:
            # [시, 분, 초]
            return time(hour=t[0], minute=t[1], second=t[2])
        elif len(t) >= 4:
            # [시, 분, 초, 나노초] - 나노초는 무시
            return time(hour=t[0], minute=t[1], second=t[2])
        else:
            raise ValueError(f"Invalid time array format: {t}")

    # 문자열 형식인 경우
    if isinstance(t, str):
        # "HH:MM:SS" 형식 시도
        try:
            return datetime.strptime(t, "%H:%M:%S").time()
        except ValueError:
            pass

        # "HH:MM" 형식 시도
        try:
            return datetime.strptime(t, "%H:%M").time()
        except ValueError:
            pass

    # 모두 실패하면 에러 메시지와 함께 예외 발생
    raise ValueError(f"Unable to parse time value: '{t}' (type: {type(t)}). Expected format: 'HH:MM:SS', 'HH:MM', or [HH, MM]")


def _format_time(t: time) -> str:
    return t.strftime("%H:%M:%S")


def find_non_overlapping_time(
    existing_blocks: List[Dict[str, Any]],
    timeTableId: int,
    duration_minutes: int = 90,
) -> Tuple[str, str]:
    """
    같은 timeTableId 내에서 겹치지 않는 시간 구간을 찾는다.
    - 기존 블록들의 시간과 겹치지 않는 첫 구간을 리턴.
    - 못 찾으면 DAY_START 기준으로 쭉 뒤로 밀어서 배치.
    """

    duration = timedelta(minutes=duration_minutes)
    today = datetime.today().date()

    # 해당 timeTableId 의 블록만 필터링해서 datetime 구간으로 변환
    used: List[Tuple[datetime, datetime]] = []
    for b in existing_blocks:
        if b.get("timeTableId") != timeTableId:
            continue

        start_dt = datetime.combine(today, _parse_time(b["blockStartTime"]))
        end_dt = datetime.combine(today, _parse_time(b["blockEndTime"]))
        used.append((start_dt, end_dt))

    used.sort(key=lambda x: x[0])

    candidate = datetime.combine(today, DAY_START)
    day_end_dt = datetime.combine(today, DAY_END)

    # 1) DAY_START 기준으로 빈 구간 찾기
    for u_start, u_end in used:
        # candidate ~ candidate+duration 이 u_start 전에 끝날 수 있으면 거기 배치
        if candidate + duration <= u_start:
            return _format_time(candidate.time()), _format_time((candidate + duration).time())

        # 아니면 candidate 를 u_end 뒤로 미룸
        if candidate < u_end:
            candidate = u_end

    # 2) 마지막 블록 뒤로 배치 (DAY_END 안에서만)
    if candidate + duration <= day_end_dt:
        return _format_time(candidate.time()), _format_time((candidate + duration).time())

    # 3) 실패시 그냥 fallback
    return "19:00:00", "20:30:00"


def calculate_end_time(start_time_str: str, duration_minutes: int = 90) -> str:
    """
    start_time_str 에 duration_minutes 를 더해서 end_time_str 리턴.
    """
    today = datetime.today().date()
    start_dt = datetime.combine(today, _parse_time(start_time_str))
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return end_dt.strftime("%H:%M:%S")


def call_google_places(query: str, location: Optional[str] = None, radius: int = 5000, result_index: int = 0) -> Optional[Dict[str, Any]]:
    """
    Google Places Text Search API 호출.
    결과 없으면 None.

    Args:
        query: 검색 키워드
        location: 중심 좌표 "latitude,longitude" 형식 (예: "37.5665,126.9780")
        radius: 검색 반경 (미터 단위, 기본값: 5km)
        result_index: 결과 리스트에서 가져올 인덱스 (0부터 시작, 기본값: 0)
    """
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": settings.google_places_api_key,
        "language": "ko",
    }

    # 위치 기반 검색 추가
    if location:
        params["location"] = location
        params["radius"] = radius
        print(f"[SEARCH] 위치 기반 검색: {location}, 반경 {radius}m")

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        if data.get("status") != "OK":
            return None

        results = data.get("results") or []
        if not results:
            return None

        # result_index가 범위를 벗어나면 마지막 결과 사용
        if result_index >= len(results):
            result_index = len(results) - 1

        item = results[result_index]

        place_data = {
            "placeName": item.get("name"),
            "placeRating": item.get("rating", 0.0),
            "placeAddress": item.get("formatted_address"),
            "placeId": item.get("place_id"),
            "xLocation": item["geometry"]["location"]["lng"],
            "yLocation": item["geometry"]["location"]["lat"],
            "placeLink": f"https://www.google.com/maps/place/?q=place_id:{item['place_id']}",
        }

        print(f"[SEARCH] 장소 찾음 (결과 {result_index+1}번째): {place_data['placeName']}")

        return place_data
    except Exception:
        return None


def detect_place_category(query: str) -> int:
    """
    한국어 쿼리로 카테고리 추론.
    - 2: 식당/맛집/카페 등
    - 1: 숙소/호텔/게스트하우스 등
    - 0: 관광 일반
    """
    q = query.lower()

    # 숙소 / 호텔 / 게스트하우스 / 모텔 / 펜션
    if any(k in q for k in ["숙소", "호텔", "게스트하우스", "모텔", "펜션", "stay"]):
        return 1  # 숙소

    # 맛집 / 식당 / 카페 / 음식 / 저녁 / 점심 / 회집 / 회
    if any(k in q for k in ["맛집", "식당", "카페", "음식", "저녁", "점심", "회집", "회 "]):
        return 2  # 식당

    # 기본은 관광지
    return 0


def search_and_create_place_block(
    query: str,
    timeTableId: int,
    planContext: dict,
    duration_minutes: int = 90,
) -> Dict[str, Any]:
    """
    단일 장소를 Google Places API로 검색하고 일정에 추가할 블록을 생성합니다.

    사용자가 "명동 맛집 추가해줘", "경복궁 일정에 넣어줘" 같은 요청을 할 때 사용하세요.
    이 함수는 1개의 장소만 검색합니다.

    Args:
        query: 검색할 장소 이름 (예: "명동 맛집", "경복궁")
        timeTableId: 추가할 타임테이블 ID
        planContext: 현재 계획 컨텍스트
        duration_minutes: 방문 시간 (기본 90분)

    Returns:
        생성된 장소 블록 정보 또는 에러
    """

    existing_blocks = parse_blocks_from_plan(planContext)

    # planContext에서 위치 정보 가져오기
    location = get_location_from_plan(planContext, timeTableId)

    # 위치 기반 검색 수행
    google_place = call_google_places(query, location=location)

    if google_place is None:
        return {"error": "NO_PLACE_FOUND"}

    start_str, end_str = find_non_overlapping_time(
        existing_blocks=existing_blocks,
        timeTableId=timeTableId,
        duration_minutes=duration_minutes,
    )

    place_category = detect_place_category(query)

    block = {
        "blockId": -1,
        "placeName": google_place["placeName"],
        "placeTheme": "",
        "placeRating": google_place["placeRating"],
        "placeAddress": google_place["placeAddress"],
        "placeLink": google_place["placeLink"],
        "blockStartTime": start_str,
        "blockEndTime": end_str,
        "xLocation": google_place["xLocation"],
        "yLocation": google_place["yLocation"],
        "placeId": google_place["placeId"],
        "placeCategoryId": place_category,
        "timeTableId": timeTableId,
    }

    return block


def search_multiple_place_blocks(
    queries: List[str],
    timeTableId: int,
    planContext: dict,
    duration_minutes: int = 90,
) -> List[Dict[str, Any]]:
    """
    여러 장소를 한 번에 Google Places API로 검색하고 일정에 추가할 블록들을 생성합니다.

    사용자가 "명동 맛집 3곳 추가해줘", "서울 관광지 5개 찾아줘" 같은 요청을 할 때 사용하세요.
    이 함수는 여러 장소를 검색하고 시간이 겹치지 않게 순차적으로 배치합니다.

    Args:
        queries: 검색할 장소 이름 리스트 (예: ["명동 맛집1", "명동 맛집2", "명동 맛집3"])
        timeTableId: 추가할 타임테이블 ID
        planContext: 현재 계획 컨텍스트
        duration_minutes: 각 장소 방문 시간 (기본 90분)

    Returns:
        생성된 장소 블록들의 리스트
    """
    existing_blocks = parse_blocks_from_plan(planContext)
    blocks: List[Dict[str, Any]] = []

    # planContext에서 위치 정보 가져오기
    location = get_location_from_plan(planContext, timeTableId)

    # 첫 번째 블록 시작 시간은 기존 블록 기준으로 비어 있는 첫 구간
    first_start_str, _ = find_non_overlapping_time(
        existing_blocks=existing_blocks,
        timeTableId=timeTableId,
        duration_minutes=duration_minutes,
    )
    today = datetime.today().date()
    current_start_dt = datetime.combine(today, _parse_time(first_start_str))
    duration = timedelta(minutes=duration_minutes)

    # 같은 쿼리가 반복되는 경우를 추적하여 다른 결과를 가져오기
    query_count = {}  # 각 쿼리별 사용된 횟수 추적

    for q in queries:
        # 이 쿼리가 몇 번째로 사용되는지 계산
        result_index = query_count.get(q, 0)
        query_count[q] = result_index + 1

        # 위치 기반 검색 수행 (같은 쿼리면 다른 인덱스 사용)
        google_place = call_google_places(q, location=location, result_index=result_index)
        if google_place is None:
            continue

        start_dt = current_start_dt
        end_dt = start_dt + duration

        # DAY_END 넘어가면 더 이상 배치하지 않음
        if end_dt.time() > DAY_END:
            break

        start_str = _format_time(start_dt.time())
        end_str = _format_time(end_dt.time())

        place_category = detect_place_category(q)

        block = {
            "blockId": -1,
            "placeName": google_place["placeName"],
            "placeTheme": "",
            "placeRating": google_place["placeRating"],
            "placeAddress": google_place["placeAddress"],
            "placeLink": google_place["placeLink"],
            "blockStartTime": start_str,
            "blockEndTime": end_str,
            "xLocation": google_place["xLocation"],
            "yLocation": google_place["yLocation"],
            "placeId": google_place["placeId"],
            "placeCategoryId": place_category,
            "timeTableId": timeTableId,
        }

        blocks.append(block)
        current_start_dt = end_dt  # 다음 블록 시작을 방금 끝난 시간으로 이동

    return blocks
