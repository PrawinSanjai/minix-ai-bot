import logging
from typing import Optional

from config import Configuration
from clients.gllm import generate_response_from_llm, stream_response_from_llm
from llm_utils.llm_prompt import get_tone_instruction, EMOTION_PATTERNS, TONE_RESPONSES

logger = logging.getLogger(name="[Minix][LLM Service]")
config = Configuration()


class LLM_Service():
    SERVICE_UNAVAILABLE_MESSAGE = "Minix's AI service is currently unavailable. Please try again later."

    def build_prompt(self, user_message: str, tone: str, conversation_history: str = "", rag_context: str = "") -> str:
        system = get_tone_instruction(tone)
        if rag_context:
            system += f"\n\nRelevant context from past conversations:\n{rag_context}"
        prompt_parts = [system, "\n\n---\n"]
        if conversation_history:
            prompt_parts.append(f"Current conversation:\n{conversation_history}\n")
        prompt_parts.extend([f"User: {user_message}", "\nMinix:"])
        return "\n".join(prompt_parts)


    def stream_chat_response(self, user_message: str, tone: str, conversation_history: str = "", rag_context: str = "", on_chunk=None) -> tuple[str, str]:
        emotion = self.detect_emotion(user_message)
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "None":
            if on_chunk:
                on_chunk(self.SERVICE_UNAVAILABLE_MESSAGE)
            return self.SERVICE_UNAVAILABLE_MESSAGE, emotion

        prompt = self.build_prompt(user_message, tone, conversation_history, rag_context)
        chunks = []
        llm_config = {"model": "gemini-2.5-flash", "thinking_budget": 0, "temperature": 0.0}
        for chunk in stream_response_from_llm(llm_config=llm_config, contents=prompt):
            chunks.append(chunk)
            if on_chunk:
                on_chunk(chunk)
        reply = "".join(chunks).strip()
        if not reply:
            raise ValueError("Gemini returned an empty response")
        return reply, emotion


    def summarize_conversation(self, existing_summary: str, transcript: str) -> str:
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "None":
            return existing_summary
        prompt = (
            "Update the private memory summary for a supportive chat. Keep only stable, useful facts, "
            "user-stated preferences, and ongoing topics. Do not diagnose, infer sensitive traits, or "
            "treat assistant suggestions as facts. Preserve uncertainty and write in neutral third person. "
            "Return a concise summary under 180 words.\n\n"
            f"Existing summary:\n{existing_summary or '(none)'}\n\nRecent conversation:\n{transcript}"
        )
        result = generate_response_from_llm(
            llm_config={"model": "gemini-2.5-flash", "thinking_budget": 0, "temperature": 0.0},
            contents=prompt,
        )
        return result[:2000]

    def generate_llm_response(
            self, user_message: str, tone: str, conversation_history: str = "", rag_context: str = "",
    ) -> Optional[str]:
        try:
            prompt = self.build_prompt(user_message, tone, conversation_history, rag_context)

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
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "None":
            return self.SERVICE_UNAVAILABLE_MESSAGE, emotion

        llm_reply = self.generate_llm_response(user_message, tone, conversation_history, rag_context)
        if llm_reply:
            return llm_reply, emotion

        return self.generate_fallback_response(tone, emotion), emotion
