from typing import Dict, Any
import json
import re

from app.models import ChatBotActionResponse, AIResponse
from app.services.gemini import gemini_model
from app.services import chatbot_service as plan_actions

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
    
    print(f"--- Gemini Full Prompt for Plan ID {plan_id} ---")
    print(full_message)
    print("-------------------------------------------------")
    
    if gemini_model is None:
        return plan_actions.simple_message("Gemini 모델이 설정되지 않았습니다. AI 서비스를 사용할 수 없습니다.")

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
            return plan_actions.simple_message("AI 응답을 받지 못했습니다.")

        # 3. AI 응답 파싱
        # Gemini가 응답 스키마를 따르도록 설정했으므로, 텍스트가 바로 JSON이라고 가정하고 파싱
        try:
            ai_data_dict = json.loads(ai_response_text)
            ai_response_data = AIResponse(**ai_data_dict)
        except (json.JSONDecodeError, ValueError, Exception) as e:
             print(f"JSON 파싱 실패: {e}\nRaw AI Text: {ai_response_text}")
             # 파싱 실패 시, 텍스트를 단순 메시지로 간주하고 반환
             return plan_actions.simple_message(f"AI가 응답했지만 구조를 알 수 없습니다: {ai_response_text}")

        
        # 4. Action 실행 (Python에서 Action을 실행하고 결과를 Java에 전달할지)
        # -> Java 서버의 요청에 따라, Python은 AI가 '무슨 Action을 해야 하는지' 결정한 결과를 
        #    ChatBotActionResponse 형태로 반환하고, 실제 실행은 Java가 담당해야 합니다.
        #    따라서, 여기서 Action 실행 코드는 제외하고, 결정된 Action 데이터를 그대로 반환합니다.
        
        # Action이 있다면 ActionData를 포함하여 반환, 없다면 단순 메시지 반환
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

    except Exception as e: # pragma: no cover
        print(f"!!! Gemini API 호출 오류: {e}")
        return plan_actions.simple_message(f"AI 챗봇 서비스 호출 중 오류 발생: {e}")