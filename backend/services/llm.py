import logging
from typing import Optional

from config import Configuration

logger = logging.getLogger(__name__)
config = Configuration()

# ─── Tone system instructions ───

TONE_INSTRUCTIONS = {
    "friendly": (
        "You are Minix, a warm and supportive emotional AI companion. "
        "You respond with gentle empathy, validation, and kindness. "
        "You make the user feel heard and understood. "
        "Keep responses conversational, warm, and supportive."
    ),
    "motivational": (
        "You are Minix, an encouraging and empowering emotional AI companion. "
        "You inspire the user to find their inner strength. "
        "You use positive, uplifting language while still being empathetic. "
        "You help the user see possibilities and build confidence."
    ),
    "listener": (
        "You are Minix, a reflective and empathetic emotional AI companion. "
        "You focus on deeply understanding the user's feelings. "
        "You ask thoughtful questions and reflect back what you hear. "
        "You create space for the user to explore their emotions."
    ),
}

DEFAULT_TONE = (
    "You are Minix, a caring emotional AI companion. "
    "You provide a safe, judgment-free space for users to express their feelings. "
    "You are empathetic, supportive, and thoughtful."
)


def get_tone_instruction(tone: str) -> str:
    return TONE_INSTRUCTIONS.get(tone, DEFAULT_TONE)


# ─── LLM-based response generation ───

def generate_llm_response(
    user_message: str,
    tone: str,
    conversation_history: str = "",
    rag_context: str = "",
) -> Optional[str]:
    """Try to generate a response using the LLM (Gemini). Falls back to None."""
    try:
        from clients.gllm import GLLM

        system = get_tone_instruction(tone)

        if rag_context:
            system += f"\n\nRelevant context from past conversations:\n{rag_context}"

        prompt_parts = [system, "\n\n---\n"]

        if conversation_history:
            prompt_parts.append(f"Current conversation:\n{conversation_history}\n")

        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("\nMinix:")

        prompt = "\n".join(prompt_parts)

        gllm = GLLM()
        response = gllm.generate(
            model="gemini-2.5-flash",
            contents=prompt,
            temperature=0.7,
        )
        return response

    except (ImportError, ValueError, Exception) as e:
        logger.warning(f"[LLM] Gemini unavailable, using fallback: {e}")
        return None


# ─── Template fallback responses ───

EMOTION_PATTERNS = [
    ("stressed", ["stress", "overwhelm", "exhaust", "tire", "drain", "burnout", "pressure", "burden"]),
    ("anxious", ["anxi", "worr", "nervous", "panic", "fear", "scared", "dread", "uneasy", "restless"]),
    ("sad", ["sad", "depress", "unhappy", "lonely", "grief", "heart", "miss", "cry", "tear", "blue", "down"]),
    ("angry", ["angry", "anger", "frustrat", "annoy", "irritat", "mad", "rage", "upset"]),
    ("happy", ["happy", "glad", "joy", "grateful", "thank", "bless", "wonder", "amaz", "great", "love", "excite"]),
    ("seeking", ["hopeless", "help", "guid", "confus", "lost", "direction", "purpose"]),
]

TONE_RESPONSES = {
    "friendly": {
        "stressed": "It sounds like you're carrying a lot right now. That's completely understandable. Would it help to talk about what's been the most challenging part? Sometimes just naming it can lighten the load a little.",
        "anxious": "Anxiety can feel so suffocating, can't it? I want you to know that what you're feeling is real and valid. Let's take a moment together — what's one small thing that feels manageable right now?",
        "sad": "I'm so sorry you're feeling this pain. It takes courage to express it. You don't have to face it alone — I'm right here with you. Would you like to tell me more about what's hurting?",
        "angry": "That sounds really frustrating. It's completely okay to feel angry about this. Sometimes letting those feelings out is the first step toward feeling better. What happened?",
        "happy": "That's wonderful to hear! It's so important to celebrate these positive moments. What's making you feel this way? I'd love to share in your joy.",
        "seeking": "It sounds like you're looking for answers or direction right now. That's a brave place to be. What area of your life feels most uncertain? Let's explore it together.",
        "neutral": "Thank you for sharing that with me. I appreciate your openness. Can you tell me a little more about how that makes you feel?",
    },
    "motivational": {
        "stressed": "You've handled hard things before, and you'll get through this too. Take a pause, breathe, and remember — you're stronger than you know. What's one step you can take right now to care for yourself?",
        "anxious": "Fear is just excitement without the breath. You've got this. Trust yourself the way I trust you. What's the smallest thing you can do right now to feel more grounded?",
        "sad": "This moment is hard, but it's just a moment — not your whole story. You have so much strength inside you. Let's find one small light together. What usually brings you comfort?",
        "angry": "Your fire is a gift. Let's channel that energy into something that moves you forward. What would make this situation better, even just a little?",
        "happy": "Yes! This energy is everything. Hold onto this moment — you deserve every bit of it. Let's build on this positivity!",
        "seeking": "Not knowing is the beginning of all discovery. You're exactly where you need to be. Let's figure this out step by step. What does your intuition tell you?",
        "neutral": "Every conversation is a step forward. I believe in you. What's one thing you'd love to accomplish or feel today?",
    },
    "listener": {
        "stressed": "I hear the weight in your words. You don't need to fix anything right now — just being heard can help. Tell me more about what's going on. I'm listening.",
        "anxious": "I'm here with you in this moment. There's no rush, no judgment. Take your time. What does this anxiety feel like in your body?",
        "sad": "I can feel the depth of what you're experiencing. You're not alone in this. I'm holding space for you. Would you like to sit with this feeling together?",
        "angry": "I can hear how much this matters to you. Your feelings are completely justified. I'm here to listen to every bit of it if you want to share.",
        "happy": "I can feel your joy and it's beautiful. Tell me everything — I want to understand what made you feel this way. These moments are precious.",
        "seeking": "You're reflecting deeply, and that's a sign of growth. Let's sit with these questions together. What answer feels truest to your heart?",
        "neutral": "I appreciate you sharing this with me. I'm here to listen deeply. What else comes to mind when you sit with this?",
    },
}


def detect_emotion(text: str) -> str:
    lower = text.lower()
    for emotion, keywords in EMOTION_PATTERNS:
        if any(kw in lower for kw in keywords):
            return emotion
    return "neutral"


def generate_fallback_response(tone: str, emotion: str) -> str:
    tone_map = TONE_RESPONSES.get(tone, TONE_RESPONSES["friendly"])
    return tone_map.get(emotion, tone_map["neutral"])


# ─── Main response generator ───

def generate_chat_response(
    user_message: str,
    tone: str,
    conversation_history: str = "",
    rag_context: str = "",
) -> tuple[str, str]:
    """Generate a response using LLM if available, falling back to templates.
    Returns (response_text, detected_emotion)."""
    emotion = detect_emotion(user_message)

    # Try LLM first
    llm_reply = generate_llm_response(user_message, tone, conversation_history, rag_context)
    if llm_reply:
        return llm_reply, emotion

    # Fallback to template
    return generate_fallback_response(tone, emotion), emotion
