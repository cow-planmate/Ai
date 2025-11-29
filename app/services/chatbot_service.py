from app.services.search_service import (
    search_and_create_place_block,
    search_multiple_place_blocks
)
from app.models import ChatBotActionResponse, ActionData
from app.services.gemini import gemini_model
from datetime import datetime, timedelta
import json
import re


def handle_java_chatbot_request(planId, message, systemPromptContext, planContext, previousPrompts=None):

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
