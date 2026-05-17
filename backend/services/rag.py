import json
import math
import re
from collections import Counter
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from models import Message, MessageEmbedding, User


# ─── Embedding helpers ───

def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def _compute_tfidf_vector(text: str, vocab: dict[str, int] | None = None) -> dict[str, float]:
    """Compute a TF-IDF-like vector for a text."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    tf = Counter(tokens)
    max_freq = max(tf.values())
    vec = {}
    for word, count in tf.items():
        if vocab is None or word in vocab:
            vec[word] = count / max_freq
    return vec


def _cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) | set(v2))
    n1 = math.sqrt(sum(v * v for v in v1.values()))
    n2 = math.sqrt(sum(v * v for v in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def keyword_search(db: Session, query: str, user_id: int, limit: int = 5) -> list[dict]:
    """Search messages by keyword relevance (always available fallback)."""
    tokens = _tokenize(query)
    if not tokens:
        return []

    # Get all user messages with their embeddings
    results = (
        db.query(Message)
        .join(MessageEmbedding, Message.id == MessageEmbedding.message_id, isouter=True)
        .filter(Message.conversation_id.in_(
            db.query(Message.conversation_id)
            .join(Conversation)
            .filter(Conversation.user_id == user_id)
        ))
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )

    if not results:
        return []

    # Score by keyword overlap
    scored = []
    for msg in results:
        msg_tokens = _tokenize(msg.content)
        overlap = len(set(tokens) & set(msg_tokens))
        if overlap > 0:
            scored.append((overlap, msg))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    return [
        {"message_id": msg.id, "content": msg.content[:300], "role": msg.role, "score": score}
        for score, msg in top
    ]


def embedding_search(db: Session, query_embedding: list[float], user_id: int, limit: int = 5) -> list[dict]:
    """Search by cosine similarity against stored embeddings."""
    stored = (
        db.query(MessageEmbedding)
        .filter(MessageEmbedding.user_id == user_id)
        .all()
    )

    scored = []
    for se in stored:
        try:
            stored_vec = json.loads(se.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        sim = _cosine_similarity(
            {str(i): v for i, v in enumerate(query_embedding)},
            {str(i): v for i, v in enumerate(stored_vec)},
        )
        if sim > 0.3:
            msg = db.query(Message).filter(Message.id == se.message_id).first()
            if msg:
                scored.append((sim, msg))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"message_id": msg.id, "content": msg.content[:300], "role": msg.role, "score": round(score, 4)}
        for score, msg in scored[:limit]
    ]


# ─── External embedding via Gemini ───

def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding vector using Gemini if available."""
    try:
        from clients.gllm import GLLM
        gllm = GLLM()
        return gllm.embed(text)
    except (ImportError, ValueError, Exception) as e:
        print(f"[RAG] Embedding unavailable: {e}")
        return None


def store_embedding(db: Session, message_id: int, user_id: int, embedding: list[float]):
    """Store or update embedding for a message."""
    existing = db.query(MessageEmbedding).filter(MessageEmbedding.message_id == message_id).first()
    if existing:
        existing.embedding = json.dumps(embedding)
    else:
        db.add(MessageEmbedding(
            message_id=message_id,
            user_id=user_id,
            embedding=json.dumps(embedding),
        ))


# ─── Main RAG search ───

def search_relevant_context(db: Session, query: str, user_id: int, limit: int = 3) -> str:
    """Search for relevant past context using keyword + optional embedding search."""
    # Keyword search always works
    results = keyword_search(db, query, user_id, limit=limit)

    # Try embedding search if Gemini is available
    embedding = generate_embedding(query)
    if embedding:
        embed_results = embedding_search(db, embedding, user_id, limit=limit)
        # Merge results, preferring embedding matches
        seen_ids = set(r["message_id"] for r in results)
        for r in embed_results:
            if r["message_id"] not in seen_ids and len(results) < limit:
                results.append(r)
                seen_ids.add(r["message_id"])

    if not results:
        return ""

    context_parts = []
    for r in results:
        role_label = "User" if r["role"] == "user" else "Minix"
        context_parts.append(f"[{role_label}]: {r['content']}")

    return "\n\n".join(context_parts)


# ─── Build conversation history for LLM prompt ───

def build_conversation_history(messages: list[Message], max_turns: int = 10) -> str:
    """Format recent conversation messages for the LLM prompt."""
    recent = messages[-max_turns:] if len(messages) > max_turns else messages
    parts = []
    for msg in recent:
        role_label = "User" if msg.role == "user" else "Minix"
        parts.append(f"{role_label}: {msg.content}")
    return "\n".join(parts)


# Import here to avoid circular import
from models import Conversation
