from typing import Optional, Dict, Any, Union, List
import json
import re

# app.models에서 필요한 모델들을 임포트한다고 가정
from app.models import (
    ChatBotActionResponse,
    AIResponse,
)
from app.services.gemini import gemini_model


def simple_message(message: str) -> ChatBotActionResponse:
    return ChatBotActionResponse(userMessage=message, hasAction=False, actions=[])


def robust_json_parse(text: str) -> Union[Dict[str, Any], str]:
    """
    JSON 문자열을 안전하게 파싱합니다. 파싱 실패 시, 깨진 JSON을 복구하여 재시도하고 상세 로그를 출력합니다.
    """
    if not isinstance(text, str):
        return text

    try:
        # 1. 일반 JSON 파싱 시도
        return json.loads(text)
    except json.JSONDecodeError as initial_e:
        print(f"⚠️ JSON 파싱 실패 (1차): {initial_e}. 입력 문자열: '{text}'")

        # 비표준 JSON 오류 유형 확인 (로그 강화)
        if "property name enclosed in double quotes" in str(initial_e):
            print("🚨 오류 유형: 키 이름에 큰따옴표가 누락된 비표준 JSON입니다.")

        try:
            # 2. 파싱 실패 시, 앞뒤 공백과 큰따옴표를 제거
            cleaned_str = text.strip().strip('"')

            # 3. 중괄호({})가 누락된 경우를 가정하여 복구 시도
            if cleaned_str and not (cleaned_str.startswith('{') and cleaned_str.endswith('}')):
                repaired_str = '{' + cleaned_str + '}'
                return json.loads(repaired_str)
            else:
                repaired_str = text
                raise json.JSONDecodeError("Manual repair failed or not needed.", repaired_str, 0)

        except json.JSONDecodeError as inner_e:
            print(
                f"⚠️ JSON 문자열 복구 및 파싱 최종 실패. 오류: {inner_e}. 복구 시도 문자열: '{repaired_str if 'repaired_str' in locals() else cleaned_str}'")
            pass

    return text


def clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    keys_to_remove = ["title", "description", "$defs", "anyOf", "default", "$ref"]

    if isinstance(schema, dict):
        for key in keys_to_remove:
            if key in schema:
                del schema[key]

        for key, value in schema.items():
            if isinstance(value, dict) and key == "properties":
                for prop_name, prop_schema in value.items():
                    if isinstance(prop_schema, dict):
                        if "description" in prop_schema:
                            del prop_schema["description"]
                        if "anyOf" in prop_schema:
                            del prop_schema["anyOf"]
                        clean_schema(prop_schema)

            elif isinstance(value, dict):
                clean_schema(value)

            elif isinstance(value, list):
                for item in value:
                    clean_schema(item)

    return schema


def handle_java_chatbot_request(
    plan_id: int,
    message: str,
    system_prompt_context: str,
    plan_context: str
) -> ChatBotActionResponse:
    full_message = f"{system_prompt_context}\n\n"
    if plan_context:
        full_message += f"현재 계획 정보:\n{plan_context}\n\n"

    full_message += f"사용자 메시지: {message}\n"
    full_message += f"현재 계획 ID: {plan_id}"

    if gemini_model is None:
        return simple_message("Gemini 모델이 설정되지 않았습니다. AI 서비스를 사용할 수 없습니다.")

    try:
        ai_response_schema = AIResponse.model_json_schema()
        ai_response_schema = clean_schema(ai_response_schema)

        # Gemini API 호출
        response = gemini_model.generate_content(
            full_message,
            generation_config={"response_mime_type": "application/json",
                               "response_schema": ai_response_schema}
        )

        ai_response_text = getattr(response, "text", None)
        if not ai_response_text:
            return simple_message("AI 응답을 받지 못했습니다.")

        # 1차 JSON 파싱 강화: 전체 응답에 robust_json_parse 적용
        ai_data_parsed = robust_json_parse(ai_response_text)

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

    except Exception as e:
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