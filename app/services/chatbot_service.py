from typing import Optional, Dict, Any, Union
import json

from app.models import (
    ChatBotActionResponse, 
    AIResponse, 
)
from app.services.gemini import gemini_model


# --- 보조 함수: 응답 구조화에 필요한 최소한의 헬퍼 함수 ---

def simple_message(message: str) -> ChatBotActionResponse:
    """Action이 없는 단순 메시지 응답을 생성합니다."""
    return ChatBotActionResponse(userMessage=message, hasAction=False, action=None)


def clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini API 호환성을 위해 스키마에서 불필요한 필드를 재귀적으로 제거합니다."""
    # keys_to_remove에 "anyOf" 추가
    keys_to_remove = ["title", "description", "$defs", "anyOf", "default"]

    if isinstance(schema, dict):
        # 1. 최상위 레벨 필드 제거
        for key in keys_to_remove:
            if key in schema:
                del schema[key]

        # 2. properties 내의 필드 (재귀적 제거)
        for key, value in schema.items():
            if isinstance(value, dict) and key == "properties":
                # properties 딕셔너리 내부를 순회하며 title, description, anyOf 등을 제거
                for prop_name, prop_schema in value.items():
                    if isinstance(prop_schema, dict):
                        # Pydantic이 Optional을 anyOf로 변환하므로, anyOf를 여기서 제거해야 함
                        if "description" in prop_schema:
                            del prop_schema["description"]
                        if "anyOf" in prop_schema:
                            # anyOf가 제거되면, 그 안에 있던 type: ['null']이 사라지므로,
                            # Optional 필드를 null 허용 필드로 수동 변환 (선택 사항)
                            # Pydantic V1/V2에서 nullable 처리가 다르므로, 일단 필드만 제거에 집중
                            del prop_schema["anyOf"]

                            # 중첩 구조가 있다면 재귀 호출
                        clean_schema(prop_schema)

            # 다른 일반 딕셔너리 구조에도 재귀 호출
            elif isinstance(value, dict):
                clean_schema(value)

            # 리스트 내의 딕셔너리에도 재귀 호출 (예: allOf, oneOf 등)
            elif isinstance(value, list):
                for item in value:
                    clean_schema(item)

    return schema
# --- 메인 로직: Java Chatbot 요청 처리 ---

def handle_java_chatbot_request(
    plan_id: int,
    message: str,
    system_prompt_context: str,
    plan_context: str
) -> ChatBotActionResponse:
    """
    Java 서버에서 전달받은 데이터를 사용하여 Gemini API를 호출하고,
    Action을 포함한 ChatBotActionResponse를 반환합니다.
    """
    # 1. 전체 프롬프트 구성
    full_message = f"{system_prompt_context}\n\n"
    if plan_context:
        full_message += f"현재 계획 정보:\n{plan_context}\n\n"
        
    full_message += f"사용자 메시지: {message}\n"
    full_message += f"현재 계획 ID: {plan_id}"
    
    if gemini_model is None:
        return simple_message("Gemini 모델이 설정되지 않았습니다. AI 서비스를 사용할 수 없습니다.")

    try:
        # 2. Gemini API 호출
        # AIResponse 모델의 JSON 스키마를 사용하여 Gemini가 구조화된 JSON을 반환하도록 유도
        ai_response_schema = AIResponse.model_json_schema()
        ai_response_schema = clean_schema(ai_response_schema)

        response = gemini_model.generate_content(
            full_message,
            generation_config={"response_mime_type": "application/json", 
                               "response_schema": ai_response_schema} # <--- 수정된 스키마 사용
        )

        ai_response_text = getattr(response, "text", None)
        if not ai_response_text:
            return simple_message("AI 응답을 받지 못했습니다.")

        # 3. AI 응답 파싱 및 유효성 검사
        try:
            ai_data_dict = json.loads(ai_response_text)

            # --- [추가된 로직: target 필드 강제 파싱] ---
            if 'action' in ai_data_dict and ai_data_dict['action'] and 'target' in ai_data_dict['action']:
                target_value = ai_data_dict['action']['target']

                # target 값이 문자열(잘못된 JSON TEXT)인 경우, 다시 파싱 시도
                if isinstance(target_value, str):
                    try:
                        # 문자열을 JSON 객체(dict)로 변환하여 덮어쓰기
                        ai_data_dict['action']['target'] = json.loads(target_value)
                        print("ℹ️ target 필드 강제 파싱 성공.")
                    except json.JSONDecodeError:
                        # 다시 파싱 실패 시 원본 오류를 남기고 진행
                        print("⚠️ target 필드 강제 파싱 실패. 원본 문자열 유지.")
            # ---------------------------------------------

            ai_response_data = AIResponse(**ai_data_dict)

        except (json.JSONDecodeError, ValueError, Exception) as e:
             # 파싱 실패 시, 원시 응답 텍스트를 메시지에 담아 반환
             print(f"JSON 파싱 실패: {e}\nRaw AI Text: {ai_response_text}")
             return simple_message(f"AI 응답 형식에 문제가 있습니다. 오류: {e}")

        
        # 4. Action 데이터를 포함하여 최종 ChatBotActionResponse 반환 (실제 실행은 Java가 담당)
        if ai_response_data.hasAction and ai_response_data.action:
            # ActionData를 포함한 최종 ChatBotActionResponse 반환
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=True,
                action=ai_response_data.action
            )
        else:
            # Action이 없는 경우, 단순 메시지 반환
            return ChatBotActionResponse(
                userMessage=ai_response_data.userMessage,
                hasAction=False,
                action=None
            )

    except Exception as e:
        print(f"!!! Gemini API 호출 오류: {e}")
        return simple_message(f"AI 챗봇 서비스 호출 중 오류 발생: {e}")