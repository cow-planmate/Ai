import json
import logging
from typing import List, Dict
from collections import defaultdict

from app.models import (
    PricePredictionRequest, PricePredictionResponse,
    PlaceBlockVO, TimetableVO,
    DailyCostSummary, TripTotalSummary,
    FoodCostDetail, AccommodationCostDetail, CostRange
)
from app.services.gemini import gemini_model

logger = logging.getLogger("uvicorn.error")

def predict_price_service(request: PricePredictionRequest) -> PricePredictionResponse:
    headcount = request.headcount
    
    # 1. Timetable ID -> Date 매핑 생성 & 날짜 정렬
    # 예: {144: "2025-11-22", 153: "2025-11-23"}
    timetable_map = {t.timetableId: t.date for t in request.timeTables}
    sorted_dates = sorted(list(set(timetable_map.values())))
    
    # 2. 데이터를 날짜별로 그룹화
    # grouped_blocks["2025-11-22"] = [block1, block2...]
    grouped_blocks: Dict[str, List[PlaceBlockVO]] = defaultdict(list)
    
    for block in request.placeBlocks:
        # block의 timeTableId로 날짜를 찾음
        date_str = timetable_map.get(block.timeTableId)
        if date_str:
            grouped_blocks[date_str].append(block)
        else:
            logger.warning(f"Block {block.blockId} has unknown timeTableId {block.timeTableId}")

    # 3. 날짜별 비용 계산
    daily_summaries = []
    
    # 전체 여행 합계 누적용 변수
    grand_food_total = 0
    grand_accom_min = 0
    grand_accom_max = 0

    for idx, date_str in enumerate(sorted_dates):
        blocks = grouped_blocks.get(date_str, [])
        
        # 날짜별 임시 저장소
        d_foods = []
        d_accoms = []
        d_food_total = 0
        d_accom_min = 0
        d_accom_max = 0
        
        for block in blocks:
            # 카테고리 2: 식당
            if block.placeCategory == 2:
                res = _estimate_food_price(block, headcount)
                
                # 결과 파싱
                p_person = res.get("estimatedPrice", 15000)
                t_price = p_person * headcount
                
                d_foods.append(FoodCostDetail(
                    placeName=block.placeName,
                    pricePerPerson=p_person,
                    totalPrice=t_price,
                    menuExamples=res.get("menuExamples", [])
                ))
                d_food_total += t_price
            
            # 카테고리 1: 숙소
            elif block.placeCategory == 1:
                res = _estimate_accommodation_price(block, headcount)
                
                room_type = res.get("recommendedRoomTypeForHeadcount", "기본 객실")
                room_types = res.get("roomTypes", [])
                selected = next((r for r in room_types if r["type"] == room_type), None)
                
                if not selected and room_types:
                    selected = room_types[0]
                    room_type = selected["type"]
                
                if selected:
                    min_p, max_p = selected["priceRange"][0], selected["priceRange"][1]
                else:
                    min_p, max_p = 50000, 100000 # Fallback

                d_accoms.append(AccommodationCostDetail(
                    placeName=block.placeName,
                    roomType=room_type,
                    priceRange=CostRange(min=min_p, max=max_p),
                    pricePerPerson=CostRange(min=min_p // headcount, max=max_p // headcount)
                ))
                d_accom_min += min_p
                d_accom_max += max_p

        # 일별 요약 생성
        daily_summary = DailyCostSummary(
            date=date_str,
            dayNumber=idx + 1,
            foodDetails=d_foods,
            accommodationDetails=d_accoms,
            dailyTotalFood=d_food_total,
            dailyTotalAccommodationMin=d_accom_min,
            dailyTotalAccommodationMax=d_accom_max,
            dailyTotalMin=d_food_total + d_accom_min,
            dailyTotalMax=d_food_total + d_accom_max
        )
        daily_summaries.append(daily_summary)

        # 전체 합계 누적
        grand_food_total += d_food_total
        grand_accom_min += d_accom_min
        grand_accom_max += d_accom_max

    # 4. 전체 여행 요약 생성
    trip_summary = TripTotalSummary(
        totalFoodCost=grand_food_total,
        totalAccommodationMin=grand_accom_min,
        totalAccommodationMax=grand_accom_max,
        perPersonCost=CostRange(
            min=(grand_food_total + grand_accom_min) // headcount,
            max=(grand_food_total + grand_accom_max) // headcount
        ),
        groupTotalCost=CostRange(
            min=grand_food_total + grand_accom_min,
            max=grand_food_total + grand_accom_max
        )
    )

    return PricePredictionResponse(
        dailyCosts=daily_summaries,
        tripSummary=trip_summary
    )


# --- AI 호출 헬퍼 함수 (기존 로직 재사용) ---

def _estimate_food_price(block: PlaceBlockVO, headcount: int) -> dict:
    if not gemini_model: return {}
    # PlaceBlockVO의 필드를 사용하여 프롬프트 구성
    prompt = f"""
    식당명: {block.placeName}, 주소: {block.placeAddress}, 평점: {block.placeRating}
    위 정보를 바탕으로 1인당 예상 식사 비용을 추론해. 
    반드시 JSON만 출력: {{"estimatedPrice": 숫자, "menuExamples": ["메뉴1"]}}
    """
    try:
        response = gemini_model.generate_content(prompt)
        return _parse_json_response(response.text)
    except Exception as e:
        logger.error(f"Food prediction error for {block.placeName}: {e}")
        return {"estimatedPrice": 15000, "menuExamples": []}

def _estimate_accommodation_price(block: PlaceBlockVO, headcount: int) -> dict:
    if not gemini_model: return {}
    prompt = f"""
    숙소명: {block.placeName}, 주소: {block.placeAddress}, 평점: {block.placeRating}, 인원: {headcount}
    위 정보를 바탕으로 적절한 객실과 가격 범위를 추론해.
    반드시 JSON만 출력: 
    {{
        "recommendedRoomTypeForHeadcount": "타입명",
        "roomTypes": [{{"type": "타입명", "priceRange": [최소, 최대]}}]
    }}
    """
    try:
        response = gemini_model.generate_content(prompt)
        return _parse_json_response(response.text)
    except Exception as e:
        logger.error(f"Accommodation prediction error for {block.placeName}: {e}")
        return {}

def _parse_json_response(text: str) -> dict:
    try:
        text = text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except:
        return {}