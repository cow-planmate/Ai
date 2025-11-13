from typing import Optional, Dict, Any, Union
import json

from app.models import (
    ChatBotActionResponse,
    AIResponse,
)
from app.services.gemini import gemini_model

def simple_message(message: str) -> ChatBotActionResponse:
    return ChatBotActionResponse(userMessage=message, hasAction=False, action=None)


def clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    keys_to_remove = ["title", "description", "$defs", "anyOf", "default"]

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

        response = gemini_model.generate_content(
            full_message,
            generation_config={"response_mime_type": "application/json",
                               "response_schema": ai_response_schema}
        )

        ai_response_text = getattr(response, "text", None)
        if not ai_response_text:
            return simple_message("AI 응답을 받지 못했습니다.")

        try:
            ai_data_dict = json.loads(ai_response_text)
        except json.JSONDecodeError as e:
            print(f"1차 JSON 파싱 실패: {e}\nRaw AI Text: {ai_response_text}")
            return simple_message(f"AI 응답이 JSON 형식이 아닙니다: {ai_response_text}")

            # 타입 강제 변환 로직 (Pydantic 오류 방지)
        if 'action' in ai_data_dict and ai_data_dict['action'] and 'target' in ai_data_dict['action']:
            target_value = ai_data_dict['action']['target']

            if isinstance(target_value, str):
                # 중첩된 JSON 파싱 시도
                try:
                    ai_data_dict['action']['target'] = json.loads(target_value)
                except json.JSONDecodeError:
                    pass  # 파싱 실패 시 원본 문자열 유지

            elif isinstance(target_value, (int, float)):
                # 숫자일 경우: Pydantic Dictionary 기대를 충족시키기 위해 딕셔너리로 래핑
                try:
                    ai_data_dict['action']['target'] = {"value": target_value}
                except Exception:
                    pass  # 오류 발생 시 원본 값 유지 (최후의 수단)

            # 2차 Pydantic 유효성 검사 및 데이터 모델화
        try:
            ai_response_data = AIResponse(**ai_data_dict)
        except (ValueError, Exception) as e:
            print(f"Pydantic 유효성 검사 실패: {e}\nProcessed Dict: {ai_data_dict}")
            return simple_message(f"AI 응답 형식에 문제가 있습니다. 오류: {e}")

            # 최종 응답 생성
        if ai_response_data.hasAction and ai_response_data.action:
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=True,
                action=ai_response_data.action
            )
        else:
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=False,
                action=None
            )

    except Exception as e:
        print(f"!!! Gemini API 호출 오류: {e}")
        return simple_message(f"AI 챗봇 서비스 호출 중 오류 발생: {e}")