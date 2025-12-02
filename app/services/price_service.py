import json
import logging
from typing import List, Dict
from collections import defaultdict
import html as _html

from app.models import (
    PricePredictionRequest, PricePredictionResponse,
    PlaceBlockVO, TimetableVO,
    DailyCostSummary, TripTotalSummary,
    FoodCostDetail, AccommodationCostDetail, CostRange
)
from app.services.gemini import gemini_model
import time

logger = logging.getLogger("uvicorn.error")

DEFAULT_FOOD_PRICE = 15000
DEFAULT_FOOD_RANGE = (12000, 18000)
DEFAULT_ACCOM_RANGE = (50000, 100000)

_food_cache: Dict[str, Dict] = {}
_accom_cache: Dict[str, Dict] = {}
_summary_cache: Dict[str, str] = {}


def _food_cache_key(block: PlaceBlockVO) -> str:
    return f"food::{block.placeName}::{block.placeAddress}::{block.placeRating}"


def _accom_cache_key(block: PlaceBlockVO, headcount: int) -> str:
    return f"accom::{block.placeName}::{block.placeAddress}::{block.placeRating}::{headcount}"


def _summary_cache_key(block: PlaceBlockVO) -> str:
    return f"summary::{block.placeName}::{block.placeAddress}::{block.placeCategory}::{block.placeTheme}"

def predict_price_service(request: PricePredictionRequest) -> PricePredictionResponse:
    headcount = request.headcount

    food_entries = []
    food_ref_map: Dict[int, str] = {}
    food_predictions_map: Dict[int, Dict] = {}

    accom_entries = []
    accom_ref_map: Dict[int, str] = {}
    accom_predictions_map: Dict[int, Dict] = {}

    summary_entries = []
    summary_ref_map: Dict[int, str] = {}
    summary_predictions_map: Dict[int, Dict] = {}
    block_lookup: Dict[int, PlaceBlockVO] = {}

    for block in request.placeBlocks:
        block_lookup[id(block)] = block
        summary_id = f"summary_{len(summary_entries)}"
        summary_key = _summary_cache_key(block)
        cached_summary = _summary_cache.get(summary_key)
        if cached_summary:
            summary_predictions_map[id(block)] = {"summary": cached_summary}
        else:
            summary_ref_map[id(block)] = summary_id
            summary_entries.append({
                "refId": summary_id,
                "name": block.placeName,
                "address": block.placeAddress,
                "category": block.placeCategory,
                "theme": getattr(block, "placeTheme", None),
                "rating": block.placeRating,
            })

        if block.placeCategory == 2:
            ref = f"food_{len(food_entries)}"
            food_key = _food_cache_key(block)
            cached_food = _food_cache.get(food_key)
            if cached_food:
                food_predictions_map[id(block)] = cached_food
            else:
                food_ref_map[id(block)] = ref
                food_entries.append({
                    "refId": ref,
                    "name": block.placeName,
                    "address": block.placeAddress,
                    "rating": block.placeRating,
                })
        elif block.placeCategory == 1:
            ref = f"accom_{len(accom_entries)}"
            accom_key = _accom_cache_key(block, headcount)
            cached_accom = _accom_cache.get(accom_key)
            if cached_accom:
                accom_predictions_map[id(block)] = cached_accom
            else:
                accom_ref_map[id(block)] = ref
                accom_entries.append({
                    "refId": ref,
                    "name": block.placeName,
                    "address": block.placeAddress,
                    "rating": block.placeRating,
                    "headcount": headcount,
                })

    ai_bundle = _batch_fetch_ai_enrichments(headcount, food_entries, accom_entries, summary_entries)
    food_predictions = {item.get("refId"): item for item in ai_bundle.get("food", []) if item.get("refId")}
    accom_predictions = {item.get("refId"): item for item in ai_bundle.get("accommodation", []) if item.get("refId")}
    summary_predictions = {item.get("refId"): item for item in ai_bundle.get("summaries", []) if item.get("refId")}

    for block_id, ref in food_ref_map.items():
        data = food_predictions.get(ref)
        if data:
            food_predictions_map[block_id] = data
            block = block_lookup.get(block_id)
            if block:
                _food_cache[_food_cache_key(block)] = data

    for block_id, ref in accom_ref_map.items():
        data = accom_predictions.get(ref)
        if data:
            accom_predictions_map[block_id] = data
            block = block_lookup.get(block_id)
            if block:
                _accom_cache[_accom_cache_key(block, headcount)] = data

    for block_id, ref in summary_ref_map.items():
        data = summary_predictions.get(ref)
        if data:
            summary_predictions_map[block_id] = data
            block = block_lookup.get(block_id)
            if block:
                value = data.get("summary", "") if isinstance(data, dict) else ""
                if value:
                    _summary_cache[_summary_cache_key(block)] = value
    
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

    # map placeName -> description (generated by AI)
    place_desc_map: Dict[str, str] = {}

    for idx, date_str in enumerate(sorted_dates):
        blocks = grouped_blocks.get(date_str, [])
        
        # 날짜별 임시 저장소
        d_foods = []
        d_accoms = []
        d_food_total = 0
        d_accom_min = 0
        d_accom_max = 0
        
        for block in blocks:
            summary_data = summary_predictions_map.get(id(block))
            desc_value = summary_data.get("summary") if isinstance(summary_data, dict) else None
            desc = (desc_value or "").strip()
            if desc:
                place_desc_map[block.placeName] = desc

            # 카테고리 2: 식당
            if block.placeCategory == 2:
                pred = food_predictions_map.get(id(block))
                p_person = _resolve_food_price(pred)
                t_price = p_person * headcount
                menus = pred.get("menuExamples", []) if isinstance(pred, dict) else []
                d_foods.append(FoodCostDetail(
                    placeName=block.placeName,
                    pricePerPerson=p_person,
                    totalPrice=t_price,
                    menuExamples=menus,
                    placeDescription=desc
                ))
                d_food_total += t_price
            
            # 카테고리 1: 숙소
            elif block.placeCategory == 1:
                pred = accom_predictions_map.get(id(block))
                room_type, min_p, max_p = _resolve_accommodation_price(pred, headcount)

                d_accoms.append(AccommodationCostDetail(
                    placeName=block.placeName,
                    roomType=room_type,
                    priceRange=CostRange(min=min_p, max=max_p),
                    pricePerPerson=CostRange(min=min_p // headcount, max=max_p // headcount)
                    ,
                    placeDescription=desc
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

    # Build HTML for direct display (frontend can use this HTML instead of raw JSON)
    try:
        rendered = _build_html(daily_summaries, trip_summary, grouped_blocks, place_desc_map)
    except Exception as e:
        logger.error(f"Failed to build HTML render: {e}")
        rendered = None

    return PricePredictionResponse(
        dailyCosts=daily_summaries,
        tripSummary=trip_summary,
        renderHtml=rendered
    )


def _build_html(daily_summaries: List[DailyCostSummary], trip_summary: TripTotalSummary, grouped_blocks: Dict[str, List[PlaceBlockVO]], place_desc_map: Dict[str, str]) -> str:
    """Build a simple, safe HTML string for direct display in the frontend.
    Use minimal inline classes — front can style further if needed.
    """
    def esc(s):
        return _html.escape(str(s)) if s is not None else ''

    parts = []
    parts.append('<div class="price-summary-root">')
    parts.append('<h2 style="margin:0 0 8px 0;font-size:18px">여행 비용 요약</h2>')

    for daily in daily_summaries:
        parts.append(f'<section style="border:1px solid #e5e7eb;padding:12px;border-radius:6px;margin-bottom:12px;background:#fff">')
        parts.append(f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">')
        parts.append(f'<div><div style="font-size:13px;color:#6b7280">Day {esc(daily.dayNumber)}</div><div style="font-weight:600">{esc(daily.date)}</div></div>')
        parts.append(f'<div style="font-size:13px;color:#374151">합계: {esc(daily.dailyTotalMin)} ~ {esc(daily.dailyTotalMax)}원</div>')
        parts.append('</div>')

        # places (from grouped_blocks)
        places = grouped_blocks.get(daily.date, []) if grouped_blocks is not None else []
        parts.append('<div style="margin-bottom:8px">')
        parts.append('<div style="font-weight:600;margin-bottom:6px">이 날의 장소</div>')
        if places:
            parts.append('<ul style="margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px">')
            for p in places:
                parts.append('<li style="border:1px solid #e5e7eb;padding:8px;border-radius:6px;background:#f9fafb">')
                parts.append(f'<div style="font-weight:600">{esc(p.placeName)}</div>')
                if getattr(p, 'placeTheme', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">테마: {esc(p.placeTheme)}</div>')
                if getattr(p, 'placeAddress', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">{esc(p.placeAddress)}</div>')
                if getattr(p, 'placeRating', None) is not None:
                    parts.append(f'<div style="font-size:12px;color:#6b7280">평점: {esc(p.placeRating)}</div>')
                    # show AI-generated description for the place if available
                    pd = place_desc_map.get(p.placeName)
                    if pd:
                        parts.append(f'<div style="margin-top:6px;color:#374151">{esc(pd)}</div>')
                parts.append('</li>')
            parts.append('</ul>')
        else:
            parts.append('<div style="font-size:13px;color:#6b7280">등록된 장소가 없습니다.</div>')
        parts.append('</div>')

        # food details
        parts.append('<div style="margin-bottom:8px">')
        parts.append('<div style="font-weight:600;margin-bottom:6px">식비</div>')
        if daily.foodDetails:
            for f in daily.foodDetails:
                parts.append('<div style="border:1px solid #eef2ff;padding:8px;border-radius:6px;background:#fff">')
                parts.append(f'<div style="font-weight:600">{esc(f.placeName)}</div>')
                parts.append(f'<div style="font-size:12px;color:#6b7280">1인당: {esc(f.pricePerPerson)}원 </div>')
                if getattr(f, 'menuExamples', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">메뉴 예시: {esc(", ".join(f.menuExamples))}</div>')
                if getattr(f, 'placeDescription', None):
                    parts.append(f'<div style="margin-top:6px;color:#374151">{esc(f.placeDescription)}</div>')
                parts.append('</div>')
        else:
            parts.append('<div style="font-size:13px;color:#6b7280">식당 정보가 없습니다.</div>')
        parts.append('</div>')

        # accommodation
        parts.append('<div>')
        parts.append('<div style="font-weight:600;margin-bottom:6px">숙박</div>')
        if daily.accommodationDetails:
            for a in daily.accommodationDetails:
                parts.append('<div style="border:1px solid #eef2ff;padding:8px;border-radius:6px;background:#fff">')
                parts.append(f'<div style="font-weight:600">{esc(a.placeName)}</div>')
                if getattr(a, 'roomType', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">객실: {esc(a.roomType)}</div>')
                if getattr(a, 'priceRange', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">요금 범위: {esc(a.priceRange.min)} ~ {esc(a.priceRange.max)}원</div>')
                if getattr(a, 'pricePerPerson', None):
                    parts.append(f'<div style="font-size:12px;color:#6b7280">1인당: {esc(a.pricePerPerson.min)} ~ {esc(a.pricePerPerson.max)}원</div>')
                if getattr(a, 'placeDescription', None):
                    parts.append(f'<div style="margin-top:6px;color:#374151">{esc(a.placeDescription)}</div>')
                parts.append('</div>')
        else:
            parts.append('<div style="font-size:13px;color:#6b7280">숙박 정보가 없습니다.</div>')
        parts.append('</div>')

        parts.append('</section>')

    # trip summary
    parts.append('<section style="padding:12px;border-radius:6px;background:#fff;border:1px solid #e5e7eb">')
    parts.append('<h3 style="margin:0 0 6px 0;font-size:16px">여행 전체 요약</h3>')
    parts.append(f'<div style="font-size:13px;color:#374151">식비 합계: {esc(trip_summary.totalFoodCost)}원</div>')
    parts.append(f'<div style="font-size:13px;color:#374151">숙박 합계: {esc(trip_summary.totalAccommodationMin)} ~ {esc(trip_summary.totalAccommodationMax)}원</div>')
    parts.append(f'<div style="font-size:13px;color:#374151">1인당 예상: {esc(trip_summary.perPersonCost.min)} ~ {esc(trip_summary.perPersonCost.max)}원</div>')
    parts.append('</section>')

    parts.append('</div>')
    return '\n'.join(parts)



def _batch_fetch_ai_enrichments(headcount: int, food_items: List[Dict], accommodation_items: List[Dict], summary_items: List[Dict]) -> Dict:
    if not gemini_model:
        return {}
    if not (food_items or accommodation_items or summary_items):
        return {}

    food_json = json.dumps(food_items, ensure_ascii=False, indent=2)
    accom_json = json.dumps(accommodation_items, ensure_ascii=False, indent=2)
    summary_json = json.dumps(summary_items, ensure_ascii=False, indent=2)

    prompt = f"""
    당신은 여행 비용과 장소 요약을 한 번에 계산하는 전문 AI입니다. 입력은 여러 장소의 메타데이터이며, 반드시 JSON만 출력해야 합니다.

    - 여행 인원수(headcount): {headcount}
    - FOOD_ITEMS: {food_json}
    - ACCOMMODATION_ITEMS: {accom_json}
    - SUMMARY_ITEMS: {summary_json}

    출력 JSON 스키마 (필요한 배열만 포함):
    {{
      "food": [
        {{
          "refId": "food_0",
          "estimatedPrice": 15000,
          "priceRange": [12000, 20000],
          "menuExamples": ["대표메뉴1", "대표메뉴2"]
        }}
      ],
      "accommodation": [
        {{
          "refId": "accom_0",
          "recommendedRoomType": "패밀리룸",
          "roomTypes": [
            {{"type": "패밀리룸", "priceRange": [90000, 140000]}},
            {{"type": "스탠다드룸", "priceRange": [60000, 90000]}}
          ]
        }}
      ],
      "summaries": [
        {{
          "refId": "summary_0",
          "summary": "1-2문장으로 된 장소 설명"
        }}
      ]
    }}

    refId는 반드시 입력과 동일하게 반환하세요. 숫자는 정수로 표기하고, 정보가 없으면 해당 refId를 생략하세요.
    """

    try:
        response = gemini_model.generate_content(prompt)
        parsed = _parse_json_response(response.text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        logger.error(f"Batch Gemini call failed: {e}")
        return {}


def _resolve_food_price(pred: Dict) -> int:
    if isinstance(pred, dict):
        try:
            value = int(pred.get("estimatedPrice", DEFAULT_FOOD_PRICE))
            return value if value > 0 else DEFAULT_FOOD_PRICE
        except (TypeError, ValueError):
            return DEFAULT_FOOD_PRICE
    return DEFAULT_FOOD_PRICE


def _resolve_accommodation_price(pred: Dict, headcount: int):
    room_type = "기본 객실"
    min_p, max_p = DEFAULT_ACCOM_RANGE

    if isinstance(pred, dict):
        room_type = pred.get("recommendedRoomType") or pred.get("recommendedRoomTypeForHeadcount") or room_type
        room_types = pred.get("roomTypes") or []
        selected = None
        for entry in room_types:
            if entry.get("type") == room_type:
                selected = entry
                break
        if not selected and room_types:
            selected = room_types[0]
            room_type = selected.get("type", room_type)
        if selected:
            price_range = selected.get("priceRange") or selected.get("price_range")
            if isinstance(price_range, list) and len(price_range) == 2:
                try:
                    min_p = int(price_range[0])
                    max_p = int(price_range[1])
                except (TypeError, ValueError):
                    min_p, max_p = DEFAULT_ACCOM_RANGE

    return room_type, min_p, max_p


def _parse_json_response(text: str) -> dict:
    try:
        text = text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except:
        return {}


def _summarize_place(block: PlaceBlockVO) -> str:
    """Generate a short (1-2 sentence) human-readable description for a place using Gemini.
    Returns an empty string on failure.
    """
    if not gemini_model:
        return ""

    try:
        prompt = f"""
        장소명: {block.placeName}\n
        장소에 대해 사용자에게 보여줄 1-2문장 요약을 생성해줘.\n
        JSON만 출력: {{"summary": "요약문"}}
        """
        resp = gemini_model.generate_content(prompt)
        parsed = _parse_json_response(resp.text)
        return parsed.get("summary", "") if isinstance(parsed, dict) else ""
    except Exception as e:
        logger.error(f"Place summary generation failed for {block.placeName}: {e}")
        return ""