<<<<<<< HEAD
from app.services.search_service import (
    search_and_create_place_block,
    search_multiple_place_blocks
)
from app.models import ChatBotActionResponse, ActionData
from app.services.gemini import gemini_model
from datetime import datetime, timedelta
=======
from typing import Optional, Dict, Any, Union, List
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75
import json
import re


def handle_java_chatbot_request(planId, message, systemPromptContext, planContext, previousPrompts=None):

<<<<<<< HEAD
    # 🔹 1) Prompt 조립
    full_prompt = systemPromptContext + "\n\n"
=======
def simple_message(message: str) -> ChatBotActionResponse:
    return ChatBotActionResponse(userMessage=message, hasAction=False, actions=[])
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75

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

<<<<<<< HEAD
        if not content or not hasattr(content, "parts"):
            continue
=======
def clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    keys_to_remove = ["title", "description", "$defs", "anyOf", "default", "$ref"]
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75

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

<<<<<<< HEAD
                if "error" in block:
                    return ChatBotActionResponse(
                        userMessage="죄송합니다. 요청하신 장소를 찾을 수 없어요. Google Places API 오류가 발생했거나 검색 결과가 없습니다.",
                        hasAction=False,
                        actions=[]
                    )
=======
def handle_java_chatbot_request(
    plan_id: int,
    message: str,
    system_prompt_context: str,
    plan_context: str
) -> ChatBotActionResponse:
    full_message = f"{system_prompt_context}\n\n"
    if plan_context:
        full_message += f"현재 계획 정보:\n{plan_context}\n\n"
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75

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

<<<<<<< HEAD
        raw = raw.strip()
        data = json.loads(raw)
=======
        if not isinstance(ai_data_parsed, dict):
            # 전체 응답이 딕셔너리로 파싱되지 않았을 경우 (가장 심각한 오류)
            print(f"1차 JSON 파싱 실패 (전체 응답): 최종 파싱 실패. 원본: {ai_response_text}")
            return simple_message(f"AI 응답 전체 JSON 형식 오류. 원본: {ai_response_text}")

        ai_data_dict = ai_data_parsed

        # Action 객체가 존재하는지 확인
        raw_actions: Any = ai_data_dict.get('actions')
        if raw_actions is None and 'action' in ai_data_dict:
            raw_actions = ai_data_dict.get('action')

        normalized_actions = _normalize_actions(raw_actions)
        ai_data_dict['actions'] = normalized_actions
        ai_data_dict.pop('action', None)

        if ai_data_dict.get('hasAction') and not normalized_actions:
            ai_data_dict['hasAction'] = False

        # 2차 Pydantic 유효성 검사 및 데이터 모델화
        try:
            ai_response_data = AIResponse(**ai_data_dict)
        except (ValueError, Exception) as e:
            print(f"Pydantic 유효성 검사 실패: {e}\nProcessed Dict: {ai_data_dict}")

            raw_target_data: Any = ai_data_dict.get('actions', [])
            if isinstance(raw_target_data, list) and raw_target_data:
                target_sample = raw_target_data[0].get('target') if isinstance(raw_target_data[0], dict) else raw_target_data[0]
            else:
                target_sample = 'Target data not found'
            if isinstance(target_sample, dict):
                target_sample = json.dumps(target_sample)

            detailed_error_message = (
                f"AI 응답 형식에 문제가 있습니다. 오류: {e}. "
                f"\n\n🚨 원본 Target 데이터 (파싱 전): {target_sample}"
            )
            return simple_message(detailed_error_message)

        # 최종 응답 생성
        if ai_response_data.hasAction and ai_response_data.actions:
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=True,
                actions=ai_response_data.actions
            )
        else:
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=False,
                actions=[]
            )
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75

        return ChatBotActionResponse(
            userMessage=data.get("userMessage", ""),
            hasAction=data.get("hasAction", False),
            actions=data.get("actions", [])
        )
    except Exception as e:
<<<<<<< HEAD
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
=======
        print(f"!!! Gemini API 호출 오류: {e}")
        return simple_message(f"AI 챗봇 서비스 호출 중 오류 발생: {e}")


def _normalize_actions(raw_actions: Any) -> List[Dict[str, Any]]:
    """Ensure actions are always a list of dicts with normalized target payloads."""
    if raw_actions is None:
        return []

    actions_list = raw_actions if isinstance(raw_actions, list) else [raw_actions]
    normalized: List[Dict[str, Any]] = []

    for entry in actions_list:
        if entry is None:
            continue
        if isinstance(entry, list):
            entry = entry[0] if entry else None
        if not isinstance(entry, dict):
            print(f"⚠️ 무시된 action 엔트리 (dict 아님): {entry}")
            continue

        action_dict = entry
        target_value = action_dict.get('target')

        # target 필드가 누락된 경우 target* 프리픽스 필드를 모아서 복구
        if target_value is None and 'targetName' in action_dict:
            target_payload = {}
            keys_to_remove = []
            for key, value in action_dict.items():
                if key.startswith('target') and key not in ('target', 'targetName'):
                    target_payload[key] = value
                    keys_to_remove.append(key)

            if target_payload:
                for key in keys_to_remove:
                    del action_dict[key]
                action_dict['target'] = target_payload
                target_value = target_payload
            else:
                action_dict['target'] = {}
                target_value = action_dict['target']

        # 타입별 방어 로직
        if isinstance(target_value, list):
            if target_value:
                first = target_value[0]
                if isinstance(first, dict):
                    action_dict['target'] = first
                elif isinstance(first, str):
                    parsed = robust_json_parse(first)
                    action_dict['target'] = parsed if isinstance(parsed, dict) else {'raw_string_data': parsed}
                else:
                    action_dict['target'] = {'list_data': target_value}
            else:
                action_dict['target'] = {}
        elif isinstance(target_value, str):
            parsed_target = robust_json_parse(target_value)
            action_dict['target'] = parsed_target if isinstance(parsed_target, dict) else {'raw_string_data': parsed_target}
        elif isinstance(target_value, (int, float)):
            action_dict['target'] = {'value': target_value}
        elif target_value is None:
            action_dict['target'] = {}

        normalized.append(action_dict)

    return normalized
>>>>>>> 10e020d05e65e7107e0ea96677d9f43306d4fc75
