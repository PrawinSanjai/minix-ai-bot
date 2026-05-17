from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import ChatRequest, ChatResponse, ConversationOut, ConversationDetail, ConversationCreate
from services.auth import get_current_user
from services.rag import search_relevant_context, build_conversation_history, generate_embedding, store_embedding
from services.llm import generate_chat_response
from models import User, Conversation, Message

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ─── Welcome messages ───

WELCOME_MESSAGES = {
    "stress": "I hear you. Life can feel overwhelming sometimes. Take a deep breath — I'm here with you. What's weighing on your heart?",
    "anxiety": "I understand that anxious feeling. You're safe here. Let's work through this together. What's been worrying you?",
    "career": "Your career journey matters, and it's natural to have mixed feelings about it. What's on your mind regarding work or your professional path?",
    "relationships": "Relationships shape so much of our lives. Whether it's joy or struggle you're experiencing, I'm here to listen. What would you like to share?",
    "general": "I'm glad you're here. This is your space to express whatever comes to mind. How are you feeling right now?",
}


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
    # ── Find or create conversation ──

    conversation = None
    if payload.conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == payload.conversation_id, Conversation.user_id == user.id)
            .first()
        )

    is_new_conversation = False
    if not conversation:
        topic = payload.topic or "general"
        conversation = Conversation(
            user_id=user.id,
            title=payload.message[:50],
            topic=topic,
        )
        db.add(conversation)
        db.flush()
        is_new_conversation = True

        welcome = get_welcome(topic)
        db.add(Message(conversation_id=conversation.id, role="bot", content=welcome))
        db.flush()

    # ── Save user message ──

    user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
    db.add(user_msg)
    db.flush()

    # ── Generate embedding for user message (async-friendly, best-effort) ──

    embedding = generate_embedding(payload.message)
    if embedding:
        store_embedding(db, user_msg.id, user.id, embedding)
        db.flush()

    # ── Build RAG context from past conversations ──

    rag_context = search_relevant_context(db, payload.message, user.id, limit=3)

    # ── Build conversation history (current chat memory) ──

    all_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    conversation_history = build_conversation_history(all_messages, max_turns=10)

    # ── Generate response with RAG + conversation memory ──

    reply, emotion = generate_chat_response(
        user_message=payload.message,
        tone=user.tone,
        conversation_history=conversation_history,
        rag_context=rag_context,
    )

    # ── Save bot message ──

    bot_msg = Message(conversation_id=conversation.id, role="bot", content=reply)
    db.add(bot_msg)
    db.flush()

    # ── Store embedding for bot message too ──

    bot_embedding = generate_embedding(reply)
    if bot_embedding:
        store_embedding(db, bot_msg.id, user.id, bot_embedding)

    # ── Update conversation title from first user message ──

    if is_new_conversation or len(all_messages) <= 2:
        conversation.title = payload.message[:50]

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
