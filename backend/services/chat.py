from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.llm import LLM_Service
from services.rag import RAG_Service
from schemas import ChatRequest, ChatResponse, ConversationOut, ConversationDetail, ConversationCreate
from models import User, Conversation, Message

llm_service = LLM_Service()
rag_service = RAG_Service()

WELCOME_MESSAGES = {
    "stress": "I hear you. Life can feel overwhelming sometimes. Take a deep breath — I'm here with you. What's weighing on your heart?",
    "anxiety": "I understand that anxious feeling. You're safe here. Let's work through this together. What's been worrying you?",
    "career": "Your career journey matters, and it's natural to have mixed feelings about it. What's on your mind regarding work or your professional path?",
    "relationships": "Relationships shape so much of our lives. Whether it's joy or struggle you're experiencing, I'm here to listen. What would you like to share?",
    "general": "I'm glad you're here. This is your space to express whatever comes to mind. How are you feeling right now?",
}


class Chat_Service():
    def _get_welcome(self, topic: str | None) -> str:
        lower = (topic or "").lower()
        for key, msg in WELCOME_MESSAGES.items():
            if key in lower:
                return msg
        return WELCOME_MESSAGES["general"]


    def send_message(self, payload: ChatRequest, user: User, db: Session) -> ChatResponse:
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

            welcome = self._get_welcome(topic)
            db.add(Message(conversation_id=conversation.id, role="bot", content=welcome))
            db.flush()

        user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
        db.add(user_msg)
        db.flush()

        embedding = rag_service.generate_embedding(payload.message)
        if embedding:
            rag_service.store_embedding(db, user_msg.id, user.id, embedding)
            db.flush()

        rag_context = rag_service.search_relevant_context(db, payload.message, user.id, limit=5)

        all_messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        conversation_history = rag_service.build_conversation_history(all_messages, max_turns=30)

        reply, emotion = llm_service.generate_chat_response(
            user_message=payload.message,
            tone=user.tone,
            conversation_history=conversation_history,
            rag_context=rag_context,
        )

        bot_msg = Message(conversation_id=conversation.id, role="bot", content=reply)
        db.add(bot_msg)
        db.flush()

        bot_embedding = rag_service.generate_embedding(reply)
        if bot_embedding:
           rag_service. store_embedding(db, bot_msg.id, user.id, bot_embedding)

        if is_new_conversation or len(all_messages) <= 2:
            conversation.title = payload.message[:50]

        db.commit()
        db.refresh(conversation)

        return ChatResponse(reply=reply, conversation_id=conversation.id, emotion=emotion)


    def list_conversations(self, user: User, db: Session) -> list[ConversationOut]:
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


    def get_conversation(self, conversation_id: int, user: User, db: Session) -> Conversation:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation


    def create_conversation(self, payload: ConversationCreate, user: User, db: Session) -> Conversation:
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


    def delete_conversation(self, conversation_id: int, user: User, db: Session) -> dict:
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


    def clear_history(self, user: User, db: Session) -> dict:
        conversations = (
            db.query(Conversation)
            .filter(Conversation.user_id == user.id)
            .all()
        )
        for c in conversations:
            db.delete(c)
        db.commit()
        return {"message": "All conversations cleared"}
