"""Local embeddings and simple hybrid search for past chat messages."""

import json
import logging
import re
from threading import Lock

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import Conversation, Message, MessageEmbedding

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self) -> None:
        self._embedding_model = None
        self._model_lock = Lock()

    def _get_embedding_model(self):
        if self._embedding_model is None:
            with self._model_lock:
                if self._embedding_model is None:
                    from fastembed import TextEmbedding

                    self._embedding_model = TextEmbedding(
                        model_name="BAAI/bge-small-en-v1.5",
                    )
        return self._embedding_model

    def generate_embedding(self, text_to_embed: str) -> list[float] | None:
        try:
            vector = next(self._get_embedding_model().embed([text_to_embed]))
            return vector.tolist()
        except Exception:
            logger.warning("Could not create a message embedding", exc_info=True)
            return None

    def _generate_query_embedding(self, query: str) -> list[float] | None:
        search_text = f"Represent this sentence for searching relevant passages: {query}"
        return self.generate_embedding(search_text)

    def store_embedding(
        self,
        db: Session,
        message_id: int,
        user_id: int,
        embedding: list[float],
    ) -> None:
        stored = db.query(MessageEmbedding).filter(
            MessageEmbedding.message_id == message_id,
        ).first()
        if stored:
            stored.embedding = embedding
            return
        db.add(MessageEmbedding(
            message_id=message_id,
            user_id=user_id,
            embedding=embedding,
        ))

    def _tokenize(self, text_to_search: str) -> set[str]:
        return set(re.findall(r"\b[a-z0-9]+\b", text_to_search.lower()))

    def _keyword_search(
        self,
        db: Session,
        query: str,
        user_id: int,
        limit: int,
        exclude_message_id: int | None,
    ) -> list[dict]:
        query_words = self._tokenize(query)
        if not query_words:
            return []

        user_conversations = db.query(Conversation.id).filter(
            Conversation.user_id == user_id,
        )
        messages = db.query(Message).filter(
            Message.conversation_id.in_(user_conversations),
        )
        if exclude_message_id is not None:
            messages = messages.filter(Message.id != exclude_message_id)

        matches = []
        for message in messages.order_by(Message.created_at.desc()).limit(100):
            overlap = len(query_words & self._tokenize(message.content))
            if overlap:
                matches.append({
                    "message_id": message.id,
                    "content": message.content[:300],
                    "role": message.role,
                })
        return matches[:limit]

    def _semantic_search(
        self,
        db: Session,
        query_embedding: list[float],
        user_id: int,
        limit: int,
        exclude_message_id: int | None,
    ) -> list[dict]:
        exclusion = "AND m.id != :exclude_id" if exclude_message_id is not None else ""
        statement = text(f"""
            SELECT me.message_id, m.content, m.role
            FROM message_embeddings AS me
            JOIN messages AS m ON m.id = me.message_id
            WHERE me.user_id = :user_id
            {exclusion}
            ORDER BY me.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)
        params = {
            "user_id": user_id,
            "query_vector": json.dumps(query_embedding),
            "limit": limit,
        }
        if exclude_message_id is not None:
            params["exclude_id"] = exclude_message_id

        try:
            rows = db.execute(statement, params).fetchall()
        except SQLAlchemyError:
            logger.warning("Semantic message search failed", exc_info=True)
            return []

        return [
            {"message_id": row[0], "content": str(row[1])[:300], "role": row[2]}
            for row in rows
        ]

    def search_relevant_context(
        self,
        db: Session,
        query: str,
        user_id: int,
        limit: int = 5,
        exclude_message_id: int | None = None,
    ) -> str:
        query_embedding = self._generate_query_embedding(query)
        semantic_matches = []
        if query_embedding:
            semantic_matches = self._semantic_search(
                db,
                query_embedding,
                user_id,
                limit * 3,
                exclude_message_id,
            )

        keyword_matches = self._keyword_search(
            db,
            query,
            user_id,
            limit * 3,
            exclude_message_id,
        )
        ranked_messages = {}
        for matches in (semantic_matches, keyword_matches):
            for rank, message in enumerate(matches, start=1):
                message_id = message["message_id"]
                ranked = ranked_messages.setdefault(
                    message_id,
                    {"message": message, "score": 0},
                )
                ranked["score"] += 1 / (60 + rank)

        best_matches = sorted(
            ranked_messages.values(),
            key=lambda item: item["score"],
            reverse=True,
        )[:limit]
        context = []
        for item in best_matches:
            message = item["message"]
            speaker = "User" if message["role"] == "user" else "Minix"
            context.append(f"[{speaker}]: {message['content']}")
        return "\n\n".join(context)

    def build_conversation_history(
        self,
        messages: list[Message],
        max_turns: int = 30,
    ) -> str:
        recent_messages = messages[-max_turns:]
        lines = []
        for message in recent_messages:
            speaker = "User" if message.role == "user" else "Minix"
            lines.append(f"{speaker}: {message.content}")
        return "\n".join(lines)
