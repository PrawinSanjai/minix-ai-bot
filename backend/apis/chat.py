from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import ChatRequest, ChatResponse, ConversationOut, ConversationDetail, ConversationCreate
from services.auth import get_current_user
from models import User, Conversation, Message

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ─── Emotion detection (mirrors frontend logic) ───

EMOTION_PATTERNS = [
    ("stressed", ["stress", "overwhelm", "exhaust", "tire", "drain", "burnout", "pressure", "burden"]),
    ("anxious", ["anxi", "worr", "nervous", "panic", "fear", "scared", "dread", "uneasy", "restless"]),
    ("sad", ["sad", "depress", "unhappy", "lonely", "grief", "heart", "miss", "cry", "tear", "blue", "down"]),
    ("angry", ["angry", "anger", "frustrat", "annoy", "irritat", "mad", "rage", "upset"]),
    ("happy", ["happy", "glad", "joy", "grateful", "thank", "bless", "wonder", "amaz", "great", "love", "excite"]),
    ("seeking", ["hopeless", "help", "guid", "confus", "lost", "direction", "purpose"]),
]

WELCOME_MESSAGES = {
    "stress": "I hear you. Life can feel overwhelming sometimes. Take a deep breath — I'm here with you. What's weighing on your heart?",
    "anxiety": "I understand that anxious feeling. You're safe here. Let's work through this together. What's been worrying you?",
    "career": "Your career journey matters, and it's natural to have mixed feelings about it. What's on your mind regarding work or your professional path?",
    "relationships": "Relationships shape so much of our lives. Whether it's joy or struggle you're experiencing, I'm here to listen. What would you like to share?",
    "general": "I'm glad you're here. This is your space to express whatever comes to mind. How are you feeling right now?",
}

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


def generate_response(tone: str, emotion: str) -> str:
    tone_map = TONE_RESPONSES.get(tone, TONE_RESPONSES["friendly"])
    return tone_map.get(emotion, tone_map["neutral"])


def get_welcome(topic: str | None) -> str:
    lower = (topic or "").lower()
    for key, msg in WELCOME_MESSAGES.items():
        if key in lower:
            return msg
    return WELCOME_MESSAGES["general"]


# ─── Routes ───


@router.post("/message", response_model=ChatResponse)
def send_message(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    emotion = detect_emotion(payload.message)
    reply = generate_response(user.tone, emotion)

    conversation = None
    if payload.conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == payload.conversation_id, Conversation.user_id == user.id)
            .first()
        )

    if not conversation:
        topic = payload.topic or "general"
        title = payload.message[:50]
        conversation = Conversation(
            user_id=user.id,
            title=title,
            topic=topic,
        )
        db.add(conversation)
        db.flush()

        welcome = get_welcome(topic)
        db.add(Message(conversation_id=conversation.id, role="bot", content=welcome))
        db.flush()

    user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
    db.add(user_msg)

    bot_msg = Message(conversation_id=conversation.id, role="bot", content=reply)
    db.add(bot_msg)

    conversation.title = payload.message[:50] if len(conversation.messages) <= 2 else conversation.title

    db.commit()
    db.refresh(conversation)

    return ChatResponse(reply=reply, conversation_id=conversation.id, emotion=emotion)


@router.get("/history", response_model=list[ConversationOut])
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    result = []
    for c in conversations:
        last_user_msg = (
            db.query(Message)
            .filter(Message.conversation_id == c.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .first()
        )
        preview = last_user_msg.content[:50] if last_user_msg else ""
        time_str = c.updated_at.strftime("%H:%M") if c.updated_at else ""
        result.append(
            ConversationOut(
                id=c.id,
                title=c.title,
                topic=c.topic,
                created_at=c.created_at,
                updated_at=c.updated_at,
                preview=preview,
                time=time_str,
            )
        )
    return result


@router.get("/history/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/history", response_model=ConversationDetail)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = Conversation(
        user_id=user.id,
        title=payload.title,
        topic=payload.topic,
    )
    db.add(conversation)
    db.flush()

    for msg in payload.messages:
        db.add(
            Message(
                conversation_id=conversation.id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
            )
        )

    db.commit()
    db.refresh(conversation)
    return conversation


@router.delete("/history/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted"}


@router.delete("/history")
def clear_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .all()
    )
    for c in conversations:
        db.delete(c)
    db.commit()
    return {"message": "All conversations cleared"}
