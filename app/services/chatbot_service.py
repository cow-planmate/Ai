from app.services.search_service import (
    search_and_create_place_block,
    search_multiple_place_blocks
)
from app.services.auto_schedule import create_auto_schedule
from app.models import ChatBotActionResponse, ActionData
from app.services.gemini import gemini_model
from datetime import datetime, timedelta
import json
import re


def handle_java_chatbot_request(planId, message, systemPromptContext, planContext, previousPrompts=None):

    # 🔹 0) "N박M일 일정 생성해줘" 패턴 감지 (자동 일정 생성)
    auto_schedule_match = re.search(r'(\d+)박\s*(\d+)일.*?(?:일정|여행|생성)', message)
    if auto_schedule_match:
        nights = int(auto_schedule_match.group(1))
        days = int(auto_schedule_match.group(2))

        # 목적지 추출
        destination = planContext.get("TravelName", "서울")

        # 기존 TimeTables 개수 확인
        timeTables = planContext.get("TimeTables", [])
        existing_days = len(timeTables)

        # 시작 날짜 계산
        if existing_days > 0:
            # 첫 번째 TimeTable의 날짜 사용
            first_date = timeTables[0].get("date")
            if first_date:
                if isinstance(first_date, str):
                    start_date_obj = datetime.strptime(first_date, "%Y-%m-%d").date()
                else:
                    # list 형식 [2025, 1, 1]
                    start_date_obj = datetime(first_date[0], first_date[1], first_date[2]).date()
                start_date = start_date_obj.strftime("%Y-%m-%d")
            else:
                start_date = datetime.now().strftime("%Y-%m-%d")
        else:
            start_date = datetime.now().strftime("%Y-%m-%d")

        print(f"[AUTO_SCHEDULE] {nights}박{days}일 자동 일정 생성 시작: {destination}, {start_date}")
        print(f"[AUTO_SCHEDULE] 기존 일정: {existing_days}일차, 요청: {days}일차")

        # 자동 일정 생성 (기존 일정 고려)
        result = create_auto_schedule(
            days=days,
            start_date=start_date,
            planContext=planContext,
            destination=destination
        )

        # 기존 TimeTables에서 날짜->timeTableId 맵 생성 (기존 ID 재사용 목적)
        existing_timeTables = planContext.get("TimeTables", [])
        date_to_existing_id = {}
        for tt in existing_timeTables:
            try:
                d = tt.get("date")
                if isinstance(d, list) and len(d) >= 3:
                    # [YYYY, M, D] 형태일 경우
                    d_obj = datetime(d[0], d[1], d[2]).date()
                    d_str = d_obj.strftime("%Y-%m-%d")
                else:
                    d_str = d
                if d_str and tt.get("timeTableId"):
                    date_to_existing_id[d_str] = tt.get("timeTableId")
            except Exception:
                continue

        # 임시 ID -> 날짜 맵 생성 (새로 생성할 TimeTable용)
        temp_id_to_date = {}

        # result에서 반환된 timeTables를 순회하며, 날짜가 기존 일정에 있으면 기존 ID를 재사용하고
        # 없으면 새로 생성하는 액션을 추가합니다.
        timeTable_actions = []
        for tt_entry in result.get("timeTables", []):
            # tt_entry는 {"action": "create", "targetName": "timeTable", "target": {"date": "..."}} 형태
            tt_target = tt_entry.get("target") if isinstance(tt_entry, dict) else None
            if not tt_target:
                continue

            tt_date = tt_target.get("date")
            # 날짜 정규화
            try:
                if isinstance(tt_date, list) and len(tt_date) >= 3:
                    tt_date = datetime(tt_date[0], tt_date[1], tt_date[2]).date().strftime("%Y-%m-%d")
            except Exception:
                pass

            # 기존 ID가 있으면 재사용(액션 생성 안 함)
            if tt_date and tt_date in date_to_existing_id:
                # 기존 TimeTable이 있는 날짜는 생성하지 않음
                pass
            else:
                # 새 일차가 필요한 경우에만 create 액션 추가
                timeTable_actions.append(ActionData(
                    action="create",
                    targetName="timeTable",
                    target=tt_target
                ))

        # PlaceBlock 생성 액션 (모든 일차의 빈 시간에 추가)
        placeBlock_actions = []
        for pb in result.get("placeBlocks", []):
            # pb에 날짜 정보가 있으면 기존 timeTableId로 매핑하여 재사용
            try:
                pb_date = pb.get("date")
                if isinstance(pb_date, list) and len(pb_date) >= 3:
                    pb_date = datetime(pb_date[0], pb_date[1], pb_date[2]).date().strftime("%Y-%m-%d")

                # 기존 TimeTable이 있는 날짜면 기존 ID 사용
                if pb_date and pb_date in date_to_existing_id:
                    pb["timeTableId"] = date_to_existing_id[pb_date]
                # 새로 생성할 TimeTable의 날짜면 음수 ID 유지 (백엔드에서 날짜로 매핑)
                # else: pb["timeTableId"]는 이미 create_auto_schedule에서 설정한 음수 ID
            except Exception:
                pass

            placeBlock_actions.append(ActionData(
                action="create",
                targetName="timeTablePlaceBlock",
                target=pb
            ))

        # 모든 액션 합치기
        all_actions = timeTable_actions + placeBlock_actions

        # 메시지 생성
        if len(result['placeBlocks']) == 0:
            # 장소를 찾지 못한 경우
            user_message = f"죄송합니다. {destination} 지역의 관광지 및 맛집 정보를 찾을 수 없어요. 😢\n다른 지역명으로 시도하거나, 직접 장소를 추가해주세요!"
        elif existing_days > 0:
            # 기존 일정에 추가하는 경우
            user_message = f"{nights}박{days}일 {destination} 여행 일정을 완성했어요! 기존 일정에 {len(result['placeBlocks'])}개의 장소를 추가했습니다. ✈️"
        else:
            # 새로 일정을 만드는 경우
            user_message = f"{nights}박{days}일 {destination} 여행 일정을 만들었어요! 총 {len(result['placeBlocks'])}개의 장소를 추가했습니다. 🎉"

        return ChatBotActionResponse(
            userMessage=user_message,
            hasAction=True if len(all_actions) > 0 else False,
            actions=all_actions
        )

    # 🔹 1) Prompt 조립
    full_prompt = systemPromptContext + "\n\n"

    if previousPrompts:
        full_prompt += "### 이전 대화\n"
        for p in previousPrompts:
            full_prompt += f"User: {p['user']}\nAI: {p['ai']}\n"
        full_prompt += "\n"

    full_prompt += f"현재 계획 정보:\n{json.dumps(planContext, ensure_ascii=False)}\n\n"

    # 🔹 사용자 메시지에서 "N일차" 패턴을 찾아서 timeTableId 힌트 추가
    day_match = re.search(r'(\d+)일차', message)
    if day_match:
        day_num = int(day_match.group(1))
        timeTables = planContext.get("TimeTables", [])
        if 0 < day_num <= len(timeTables):
            timeTableId = timeTables[day_num - 1].get("timeTableId")
            full_prompt += f"힌트: 사용자가 '{day_num}일차'를 언급했습니다. 해당 timeTableId는 {timeTableId}입니다.\n\n"

    full_prompt += f"사용자 메시지: {message}\n"

    # 🔹 2) Gemini Tools 정의
    tools = [search_and_create_place_block, search_multiple_place_blocks]

    # 🔹 3) Gemini 요청
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }

    response = gemini_model.generate_content(
        full_prompt,
        tools=tools,
        generation_config=generation_config
    )

    actions = []

    # =========================================================
    # 4) Gemini Flash 2.5 방식 function_call 파싱
    # =========================================================
    for cand in response.candidates:
        content = cand.content
        print(content)

        if not content or not hasattr(content, "parts"):
            continue

        for part in content.parts:
            # function_call이 있고 None이 아닌지 확인
            if not hasattr(part, "function_call") or part.function_call is None:
                continue

            # function_call의 name이 있는지 확인
            if not hasattr(part.function_call, "name") or not part.function_call.name:
                continue

            fn_name = part.function_call.name
            args = dict(part.function_call.args) if part.function_call.args else {}

            # planContext를 올바르게 설정 (Gemini가 잘못 채운 경우 덮어쓰기)
            args["planContext"] = planContext

            # timeTableId를 int로 변환 (Gemini가 float로 보내는 경우 대비)
            if "timeTableId" in args and isinstance(args["timeTableId"], float):
                args["timeTableId"] = int(args["timeTableId"])

            # ===== 단일 검색 =====
            if fn_name == "search_and_create_place_block":
                block = search_and_create_place_block(**args)

                if "error" in block:
                    return ChatBotActionResponse(
                        userMessage="죄송합니다. 요청하신 장소를 찾을 수 없어요. Google Places API 오류가 발생했거나 검색 결과가 없습니다.",
                        hasAction=False,
                        actions=[]
                    )

                actions.append(ActionData(
                    action="create",
                    targetName="timeTablePlaceBlock",
                    target=block
                ))

            # ===== 다중 검색 =====
            elif fn_name == "search_multiple_place_blocks":
                blocks = search_multiple_place_blocks(**args)

                if len(blocks) == 0:
                    return ChatBotActionResponse(
                        userMessage="죄송합니다. 요청하신 장소를 찾을 수 없어요. Google Places API 오류가 발생했거나 검색 결과가 없습니다.",
                        hasAction=False,
                        actions=[]
                    )

                for b in blocks:
                    actions.append(ActionData(
                        action="create",
                        targetName="timeTablePlaceBlock",
                        target=b
                    ))

    # =========================================================
    # 5) function_call이 있었으면 ActionResponse 반환
    # =========================================================
    if len(actions) > 0:
        # 성공 메시지 생성
        place_names = [action.target.get("placeName", "장소") for action in actions if hasattr(action, 'target')]
        if len(place_names) > 0:
            message = f"{', '.join(place_names[:3])}{'...' if len(place_names) > 3 else ''} 일정을 추가했어요!"
        else:
            message = "요청하신 장소들을 일정에 추가했어요."

        return ChatBotActionResponse(
            userMessage=message,
            hasAction=True,
            actions=actions
        )

    # =========================================================
    # 6) function_call이 없을 경우 → LLM이 JSON 응답을 직접 생성했을 때
    # =========================================================
    try:
        raw = response.text

        # ```json ``` 코드 블록 제거
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        raw = raw.strip()
        data = json.loads(raw)

        return ChatBotActionResponse(
            userMessage=data.get("userMessage", ""),
            hasAction=data.get("hasAction", False),
            actions=data.get("actions", [])
        )
    except Exception as e:
        # JSON 파싱 실패 시, 일반 텍스트 응답으로 처리
        try:
            text_response = response.text.strip()
            if text_response:
                return ChatBotActionResponse(
                    userMessage=text_response,
                    hasAction=False,
                    actions=[]
                )
        except:
            pass

        # 완전히 실패한 경우
        return ChatBotActionResponse(
            userMessage="죄송합니다. 요청을 처리하는 중 오류가 발생했습니다.",
            hasAction=False,
            actions=[]
        )
