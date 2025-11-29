# app/services/auto_schedule.py

from datetime import datetime, time, timedelta, date as date_type
from typing import List, Dict, Any, Optional

from app.services.search_service import (
    get_location_from_plan,
    call_google_places,
    detect_place_category,
    parse_blocks_from_plan,
)


def get_existing_blocks_for_date(planContext: dict, date_str: str) -> List[Dict[str, Any]]:
    """
    planContext에서 특정 날짜의 기존 PlaceBlock들을 추출

    Args:
        planContext: 현재 계획 컨텍스트
        date_str: 날짜 문자열 "YYYY-MM-DD"

    Returns:
        해당 날짜의 PlaceBlock 리스트
    """
    all_blocks = parse_blocks_from_plan(planContext)

    # 해당 날짜의 블록만 필터링
    date_blocks = []
    for block in all_blocks:
        block_date = block.get("date")

        # 날짜 형식 통일 (문자열로 변환)
        if isinstance(block_date, list):
            # [2025, 1, 1] 형식
            block_date_str = f"{block_date[0]:04d}-{block_date[1]:02d}-{block_date[2]:02d}"
        elif isinstance(block_date, str):
            block_date_str = block_date
        else:
            continue

        if block_date_str == date_str:
            date_blocks.append(block)

    return date_blocks


def has_time_conflict(existing_blocks: List[Dict[str, Any]], start_time: str, end_time: str) -> bool:
    """
    기존 블록들과 시간 겹침이 있는지 확인

    Args:
        existing_blocks: 기존 PlaceBlock 리스트
        start_time: 체크할 시작 시간 "HH:MM:SS"
        end_time: 체크할 종료 시간 "HH:MM:SS"

    Returns:
        겹치는 일정이 있으면 True, 없으면 False
    """
    if not existing_blocks:
        return False

    # 체크할 시간을 time 객체로 변환
    check_start = datetime.strptime(start_time, "%H:%M:%S").time()
    check_end = datetime.strptime(end_time, "%H:%M:%S").time()

    for block in existing_blocks:
        block_start = block.get("blockStartTime")
        block_end = block.get("blockEndTime")

        if not block_start or not block_end:
            continue

        # 문자열이면 time 객체로 변환
        if isinstance(block_start, str):
            block_start = datetime.strptime(block_start, "%H:%M:%S").time()
        if isinstance(block_end, str):
            block_end = datetime.strptime(block_end, "%H:%M:%S").time()

        # 시간 겹침 체크
        # A와 B가 겹치는 조건: A.start < B.end AND B.start < A.end
        if check_start < block_end and block_start < check_end:
            return True

    return False


def create_auto_schedule(
    days: int,
    start_date: str,
    planContext: dict,
    destination: str,
) -> Dict[str, Any]:
    """
    N박M일 자동 일정 생성

    Args:
        days: 여행 일수 (예: 3일이면 2박3일)
        start_date: 시작 날짜 "YYYY-MM-DD"
        planContext: 현재 계획 컨텍스트
        destination: 여행지 이름 (예: "서울", "부산")

    Returns:
        {
            "timeTables": [...],  # TimeTable 생성 액션
            "placeBlocks": [...]  # PlaceBlock 생성 액션
        }
    """

    time_tables = []
    place_blocks_actions = []

    # 시작 날짜 파싱
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 목적지로 기본 위치 검색 (첫 검색용)
    location = planContext.get("TravelName")

    # 숙소 처리: 1일차에 이미 숙소가 있으면 그것을 사용, 없으면 새로 검색
    accommodation_place = None
    if days > 1:  # 2일 이상일 때만 숙소 필요
        # 1일차 날짜 계산
        first_date_str = start_date_obj.strftime("%Y-%m-%d")
        first_day_blocks = get_existing_blocks_for_date(planContext, first_date_str)

        # 1일차에 숙소 시간대(21:00-23:59)에 있는 장소 찾기
        existing_accommodation = None
        for block in first_day_blocks:
            block_start = block.get("blockStartTime")
            block_end = block.get("blockEndTime")

            if block_start and block_end:
                # 문자열이면 time 객체로 변환
                if isinstance(block_start, str):
                    block_start = datetime.strptime(block_start, "%H:%M:%S").time()
                if isinstance(block_end, str):
                    block_end = datetime.strptime(block_end, "%H:%M:%S").time()

                # 21:00-23:59 시간대와 겹치는 블록 찾기
                accommodation_start = datetime.strptime("21:00:00", "%H:%M:%S").time()
                accommodation_end = datetime.strptime("23:59:00", "%H:%M:%S").time()

                if block_start < accommodation_end and accommodation_start < block_end:
                    existing_accommodation = block
                    break

        if existing_accommodation:
            # 1일차에 숙소가 있으면 그것을 사용
            accommodation_place = {
                "placeName": existing_accommodation.get("placeName"),
                "placeRating": existing_accommodation.get("placeRating", 0.0),
                "placeAddress": existing_accommodation.get("placeAddress"),
                "placeLink": existing_accommodation.get("placeLink"),
                "xLocation": existing_accommodation.get("xLocation"),
                "yLocation": existing_accommodation.get("yLocation"),
                "placeId": existing_accommodation.get("placeId"),
            }
            print(f"[AUTO_SCHEDULE] 1일차 기존 숙소 사용: {accommodation_place['placeName']}")
        else:
            # 1일차에 숙소가 없으면 새로 검색
            accommodation_place = call_google_places(
                f"{destination} 호텔",
                location=location,
                result_index=0
            )
            if accommodation_place:
                print(f"[AUTO_SCHEDULE] 숙소 새로 선정: {accommodation_place['placeName']}")

    for day in range(days):
        current_date = start_date_obj + timedelta(days=day)
        date_str = current_date.strftime("%Y-%m-%d")

        # 1. TimeTable 생성 액션 추가
        time_table_action = {
            "action": "create",
            "targetName": "timeTable",
            "target": {
                "date": date_str
            }
        }
        time_tables.append(time_table_action)

        # 2. 각 일차마다 장소 블록 생성 (임시 timeTableId 사용)
        # 실제 timeTableId는 백엔드에서 생성 후 할당됨
        temp_time_table_id = -(day + 1)  # -1, -2, -3, ...

        day_blocks = create_daily_schedule(
            day_number=day + 1,
            date_str=date_str,
            temp_time_table_id=temp_time_table_id,
            destination=destination,
            is_last_day=(day == days - 1),
            location=location,
            accommodation_place=accommodation_place,  # 같은 숙소 정보 전달
            planContext=planContext,  # 기존 일정 확인용
        )

        place_blocks_actions.extend(day_blocks)

    return {
        "timeTables": time_tables,
        "placeBlocks": place_blocks_actions,
    }


def create_daily_schedule(
    day_number: int,
    date_str: str,
    temp_time_table_id: int,
    destination: str,
    is_last_day: bool,
    location: Optional[str],
    accommodation_place: Optional[Dict[str, Any]],
    planContext: dict,
) -> List[Dict[str, Any]]:
    """
    하루 일정 생성 (오전, 점심, 저녁, 숙소)

    Args:
        day_number: 몇 일차인지
        date_str: 날짜 문자열
        temp_time_table_id: 임시 timeTableId (음수)
        destination: 여행지 이름
        is_last_day: 마지막 날인지 (숙소 생성 제외)
        location: 검색 중심 위치
        accommodation_place: 숙소 정보 (모든 날짜에 같은 숙소 사용)
        planContext: 현재 계획 컨텍스트 (기존 일정 확인용)

    Returns:
        PlaceBlock 생성 액션 리스트
    """

    blocks = []

    # 기존 일정 확인 - 해당 날짜의 기존 PlaceBlock들 파싱
    existing_blocks = get_existing_blocks_for_date(planContext, date_str)

    # 각 시간대별로 겹치는지 체크
    predefined_slots = {
        "morning": ("09:00:00", "11:00:00"),
        "lunch": ("12:00:00", "14:00:00"),
        "dinner": ("18:00:00", "20:00:00"),
        "accommodation": ("21:00:00", "23:59:00"),
    }

    # 1. 오전 관광지 (09:00-11:00)
    if not has_time_conflict(existing_blocks, *predefined_slots["morning"]):
        morning_block = create_place_block(
            query=f"{destination} 관광지",
            start_time="09:00:00",
            end_time="11:00:00",
            date_str=date_str,
            temp_time_table_id=temp_time_table_id,
            location=location,
            result_index=day_number - 1,  # 각 날마다 다른 관광지
        )
        if morning_block:
            blocks.append(morning_block)
    else:
        print(f"[AUTO_SCHEDULE] {date_str} 오전 시간대에 기존 일정이 있어 건너뜁니다.")

    # 2. 점심 맛집 (12:00-14:00)
    if not has_time_conflict(existing_blocks, *predefined_slots["lunch"]):
        lunch_block = create_place_block(
            query=f"{destination} 맛집",
            start_time="12:00:00",
            end_time="14:00:00",
            date_str=date_str,
            temp_time_table_id=temp_time_table_id,
            location=location,
            result_index=day_number - 1,
        )
        if lunch_block:
            blocks.append(lunch_block)
    else:
        print(f"[AUTO_SCHEDULE] {date_str} 점심 시간대에 기존 일정이 있어 건너뜁니다.")

    # 3. 저녁 맛집 (18:00-20:00)
    if not has_time_conflict(existing_blocks, *predefined_slots["dinner"]):
        dinner_block = create_place_block(
            query=f"{destination} 회 맛집" if day_number % 2 == 0 else f"{destination} 고기 맛집",
            start_time="18:00:00",
            end_time="20:00:00",
            date_str=date_str,
            temp_time_table_id=temp_time_table_id,
            location=location,
            result_index=day_number - 1,
        )
        if dinner_block:
            blocks.append(dinner_block)
    else:
        print(f"[AUTO_SCHEDULE] {date_str} 저녁 시간대에 기존 일정이 있어 건너뜁니다.")

    # 4. 숙소 (21:00-23:59) - 마지막 날 제외, 모든 날짜에 같은 숙소 사용
    if not is_last_day and accommodation_place:
        if not has_time_conflict(existing_blocks, *predefined_slots["accommodation"]):
            accommodation_block = create_place_block_from_data(
                place_data=accommodation_place,
                start_time="21:00:00",
                end_time="23:59:00",
                date_str=date_str,
                temp_time_table_id=temp_time_table_id,
            )
            if accommodation_block:
                blocks.append(accommodation_block)
        else:
            print(f"[AUTO_SCHEDULE] {date_str} 숙소 시간대에 기존 일정이 있어 건너뜁니다.")

    return blocks


def create_place_block(
    query: str,
    start_time: str,
    end_time: str,
    date_str: str,
    temp_time_table_id: int,
    location: Optional[str],
    result_index: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    단일 PlaceBlock 생성

    Returns:
        PlaceBlock 액션 dict 또는 None (검색 실패 시)
    """

    # Google Places API로 장소 검색
    google_place = call_google_places(query, location=location, result_index=result_index)

    if google_place is None:
        print(f"[AUTO_SCHEDULE] 장소 검색 실패: {query}")
        return None

    # 카테고리 감지
    place_category = detect_place_category(query)

    block = {
        "blockId": -1,
        "placeName": google_place["placeName"],
        "placeTheme": "",
        "placeRating": google_place["placeRating"],
        "placeAddress": google_place["placeAddress"],
        "placeLink": google_place["placeLink"],
        "blockStartTime": start_time,
        "blockEndTime": end_time,
        "xLocation": google_place["xLocation"],
        "yLocation": google_place["yLocation"],
        "placeId": google_place["placeId"],
        "placeCategoryId": place_category,
        "timeTableId": temp_time_table_id,
        "date": date_str,
    }

    print(f"[AUTO_SCHEDULE] 장소 생성: {google_place['placeName']} ({start_time}-{end_time})")

    return block


def create_place_block_from_data(
    place_data: Dict[str, Any],
    start_time: str,
    end_time: str,
    date_str: str,
    temp_time_table_id: int,
) -> Dict[str, Any]:
    """
    이미 검색된 장소 데이터로 PlaceBlock 생성 (같은 숙소를 여러 날짜에 추가할 때 사용)

    Args:
        place_data: call_google_places의 반환값
        start_time: 시작 시간
        end_time: 종료 시간
        date_str: 날짜
        temp_time_table_id: 임시 timeTableId

    Returns:
        PlaceBlock dict
    """

    # 카테고리 감지 (숙소)
    place_category = 1  # 숙소

    block = {
        "blockId": -1,
        "placeName": place_data["placeName"],
        "placeTheme": "",
        "placeRating": place_data["placeRating"],
        "placeAddress": place_data["placeAddress"],
        "placeLink": place_data["placeLink"],
        "blockStartTime": start_time,
        "blockEndTime": end_time,
        "xLocation": place_data["xLocation"],
        "yLocation": place_data["yLocation"],
        "placeId": place_data["placeId"],
        "placeCategoryId": place_category,
        "timeTableId": temp_time_table_id,
        "date": date_str,
    }

    print(f"[AUTO_SCHEDULE] 숙소 추가: {place_data['placeName']} ({start_time}-{end_time})")

    return block
