from typing import Callable

from config import Configuration
from clients.gllm import stream_text
from llm_utils.llm_prompt import get_tone_instruction, EMOTION_PATTERNS

api_key = Configuration().GEMINI_API_KEY


class LLMService:
    SERVICE_UNAVAILABLE_MESSAGE = "Minix's AI service is currently unavailable. Please try again later."

    def build_prompt(self, user_message: str, tone: str, conversation_history: str = "", rag_context: str = "") -> str:
        prompt = get_tone_instruction(tone)
        if rag_context:
            prompt += f"\n\nRelevant context from past conversations:\n{rag_context}"
        if conversation_history:
            prompt += f"\n\nCurrent conversation:\n{conversation_history}"
        return f"{prompt}\n\nUser: {user_message}\n\nMinix:"


    def stream_chat_response(
        self,
        user_message: str,
        tone: str,
        conversation_history: str = "",
        rag_context: str = "",
        on_chunk: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        emotion = self.detect_emotion(user_message)
        if not api_key or api_key == "None":
            if on_chunk:
                on_chunk(self.SERVICE_UNAVAILABLE_MESSAGE)
            return self.SERVICE_UNAVAILABLE_MESSAGE, emotion

        prompt = self.build_prompt(user_message, tone, conversation_history, rag_context)
        chunks = []
        for chunk in stream_text("gemini-2.5-flash", prompt):
            chunks.append(chunk)
            if on_chunk:
                on_chunk(chunk)
        reply = "".join(chunks).strip()
        if not reply:
            raise ValueError("Gemini returned an empty response")
        return reply, emotion


    def detect_emotion(self, text: str) -> str:
        lower = text.lower()
        for emotion, keywords in EMOTION_PATTERNS:
            if any(kw in lower for kw in keywords):
                return emotion
        return "neutral"
