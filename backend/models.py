from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    tone = Column(String(20), nullable=False, default="friendly")

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False, default="New conversation")
    topic = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
    embedding = relationship("MessageEmbedding", back_populates="message", uselist=False, cascade="all, delete-orphan")


class MessageEmbedding(Base):
    __tablename__ = "message_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    embedding = Column(Vector(384), nullable=False)

    message = relationship("Message", back_populates="embedding")


class ChatJob(Base):
    __tablename__ = "chat_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_chat_jobs_user_idempotency"),
        Index("ix_chat_jobs_conversation_status_id", "conversation_id", "status", "id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    assistant_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    emotion = Column(String(20), nullable=True)
    enqueued_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User")
    conversation = relationship("Conversation")
    user_message = relationship("Message", foreign_keys=[user_message_id])
    assistant_message = relationship("Message", foreign_keys=[assistant_message_id])


class JobOutbox(Base):
    __tablename__ = "job_outbox"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("chat_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConversationMemory(Base):
    __tablename__ = "conversation_memories"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_conversation_memories_conversation_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
