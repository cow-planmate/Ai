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
        response = gemini_model.generate_content(
            full_message,
            generation_config={"response_mime_type": "application/json", 
                               "response_schema": AIResponse.model_json_schema()}
        )

        ai_response_text = getattr(response, "text", None)
        if not ai_response_text:
            return simple_message("AI 응답을 받지 못했습니다.")

        # 3. AI 응답 파싱 및 유효성 검사
        try:
            # Pydantic 모델을 사용하여 응답 파싱 및 유효성 검사
            ai_data_dict = json.loads(ai_response_text)
            ai_response_data = AIResponse(**ai_data_dict)

        except (json.JSONDecodeError, ValueError) as e:
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