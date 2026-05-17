from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional


# ─── Auth ───

class UserRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── User ───

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool
    tone: str


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)


class ToneUpdate(BaseModel):
    tone: str = Field(pattern=r"^(friendly|motivational|listener)$")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


# ─── Chat ───

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    topic: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    preview: str = ""
    time: str = ""


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    topic: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    topic: Optional[str] = None
    messages: list[dict] = []


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[int] = None
    topic: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int
    emotion: str
