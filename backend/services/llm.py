import logging
from typing import Optional

from config import Configuration
from clients.gllm import generate_response_from_llm
from llm_utils.llm_prompt import get_tone_instruction, EMOTION_PATTERNS, TONE_RESPONSES

logger = logging.getLogger(name="[Minix][LLM Service]")
config = Configuration()


class LLM_Service():
    def generate_llm_response(
            self, user_message: str, tone: str, conversation_history: str = "", rag_context: str = "",
    ) -> Optional[str]:
        try:
            system = get_tone_instruction(tone)

            if rag_context:
                system += f"\n\nRelevant context from past conversations:\n{rag_context}"

            prompt_parts = [system, "\n\n---\n"]

            if conversation_history:
                prompt_parts.append(f"Current conversation:\n{conversation_history}\n")

            prompt_parts.append(f"User: {user_message}")
            prompt_parts.append("\nMinix:")

            prompt = "\n".join(prompt_parts)

            llm_config = {
                "model": "gemini-2.5-flash",
                "thinking_budget": 0,
                "temperature": 0.0,
            }
            response = generate_response_from_llm(llm_config=llm_config, contents=prompt)
            return response

        except (ImportError, ValueError, Exception) as e:
            logger.warning(f"Gemini unavailable, using fallback: {e}")
            return None


    def detect_emotion(self, text: str) -> str:
        lower = text.lower()
        for emotion, keywords in EMOTION_PATTERNS:
            if any(kw in lower for kw in keywords):
                return emotion
        return "neutral"


    def generate_fallback_response(self, tone: str, emotion: str) -> str:
        tone_map = TONE_RESPONSES.get(tone, TONE_RESPONSES["friendly"])
        return tone_map.get(emotion, tone_map["neutral"])


    def generate_chat_response(
            self, user_message: str, tone: str,  conversation_history: str = "", rag_context: str = "",
    ) -> tuple[str, str]:
        emotion = self.detect_emotion(user_message)
        llm_reply = self.generate_llm_response(user_message, tone, conversation_history, rag_context)
        if llm_reply:
            return llm_reply, emotion

        return self.generate_fallback_response(tone, emotion), emotion
