from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.auth import Auth_Service
from services.chat import Chat_Service
from schemas import ChatRequest, ChatResponse, ConversationOut, ConversationDetail, ConversationCreate


router = APIRouter(prefix="/chat", tags=["chat"])
auth_service = Auth_Service()
chat_service = Chat_Service()

@router.post("/message", response_model=ChatResponse)
def send_message_route(
    payload: ChatRequest,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.send_message(payload, user, db)


@router.get("/history", response_model=list[ConversationOut])
def list_conversations_route(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.list_conversations(user, db)


@router.get("/history/{conversation_id}", response_model=ConversationDetail)
def get_conversation_route(
    conversation_id: int,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.get_conversation(conversation_id, user, db)


@router.post("/history", response_model=ConversationDetail)
def create_conversation_route(
    payload: ConversationCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.create_conversation(payload, user, db)


@router.delete("/history/{conversation_id}")
def delete_conversation_route(
    conversation_id: int,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.delete_conversation(conversation_id, user, db)


@router.delete("/history")
def clear_history_route(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.clear_history(user, db)
