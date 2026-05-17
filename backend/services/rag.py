import json, re
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Message, MessageEmbedding, Conversation


class RAG_Service():

    def _tokenize(self,text: str) -> list[str]:
        return re.findall(r'\b[a-z0-9]+\b', text.lower())
    

    def keyword_search(self, db: Session, query: str, user_id: int, limit: int = 5) -> list[dict]:
        tokens = self._tokenize(query)
        if not tokens:
            return []

        conv_ids = (
            db.query(Conversation.id)
            .filter(Conversation.user_id == user_id)
            .subquery()
        )

        recent = (
            db.query(Message)
            .filter(Message.conversation_id.in_(conv_ids))
            .order_by(Message.created_at.desc())
            .limit(100)
            .all()
        )

        scored = []
        for msg in recent:
            msg_tokens = self._tokenize(msg.content)
            overlap = len(set(tokens) & set(msg_tokens))
            if overlap > 0:
                scored.append((overlap, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"message_id": msg.id, "content": msg.content[:300], "role": msg.role, "score": score}
            for score, msg in scored[:limit]
        ]
    

    def embedding_search(self, db: Session, query_embedding: list[float], user_id: int, limit: int = 5) -> list[dict]:
        """Search using pgvector cosine distance (<->)."""
        try:
            vec = json.dumps(query_embedding)
            rows = db.execute(
                text("""
                    SELECT me.message_id, m.content, m.role, me.embedding <=> :query_vec AS distance
                    FROM message_embeddings me
                    JOIN messages m ON m.id = me.message_id
                    WHERE me.user_id = :uid
                    ORDER BY distance
                    LIMIT :lim
                """),
                {"query_vec": vec, "uid": user_id, "lim": limit},
            ).fetchall()

            return [
                {"message_id": r[0], "content": str(r[1])[:300], "role": str(r[2]), "score": round(float(r[3]), 4)}
                for r in rows
            ]
        except Exception as e:
            print(f"[RAG] pgvector search failed: {e}")
            return []
    
    _model = None

    def _get_model(self):
        global _model
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        return _model
    

    def generate_embedding(self, text: str) -> list[float] | None:
        try:
            model = self._get_model()
            return list(model.embed([text]))[0].tolist()
        except Exception as e:
            print(f"[RAG] Local embedding failed: {e}")
            return None
        

    def store_embedding(self, db: Session, message_id: int, user_id: int, embedding: list[float]):
        """Store or update embedding using pgvector."""
        existing = db.query(MessageEmbedding).filter(MessageEmbedding.message_id == message_id).first()
        vec = json.dumps(embedding)
        if existing:
            db.execute(
                text("UPDATE message_embeddings SET embedding = :vec WHERE id = :id"),
                {"vec": vec, "id": existing.id},
            )
        else:
            db.execute(
                text("INSERT INTO message_embeddings (message_id, user_id, embedding) VALUES (:mid, :uid, :vec)"),
                {"mid": message_id, "uid": user_id, "vec": vec},
            )


    def search_relevant_context(self, db: Session, query: str, user_id: int, limit: int = 5) -> str:
        results = []

        embedding = self.generate_embedding(query)
        if embedding:
            results = self.embedding_search(db, embedding, user_id, limit=limit)

        if not results:
            results = self.keyword_search(db, query, user_id, limit=limit)

        if not results:
            return ""

        context_parts = []
        for r in results:
            label = "User" if r["role"] == "user" else "Minix"
            context_parts.append(f"[{label}]: {r['content']}")

        return "\n\n".join(context_parts)
    
    
    def build_conversation_history(self, messages: list[Message], max_turns: int = 30) -> str:
        recent = messages[-max_turns:] if len(messages) > max_turns else messages
        parts = []
        for msg in recent:
            label = "User" if msg.role == "user" else "Minix"
            parts.append(f"{label}: {msg.content}")
        return "\n".join(parts)
