import uuid
from sqlalchemy.orm import Session
from app.models.chat_history import ChatHistory


class ChatHistoryService:
    def __init__(self, db: Session):
        self.db = db

    def save(self, user_id: int, query: str, answer: str, source: str, session_id: str = None):
        if session_id and isinstance(session_id, str):
            try:
                session_id = uuid.UUID(session_id)
            except ValueError:
                session_id = None
                
        record = ChatHistory(
            user_id=user_id,
            query=query,
            answer=answer,
            source=source,
            session_id=session_id
        )


        self.db.add(record)
        self.db.commit()

    def get_recent(self, user_id: int, limit: int = 5):
        return (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_session(self, user_id: int, session_id: str):
        if session_id and isinstance(session_id, str):
            try:
                session_id = uuid.UUID(session_id)
            except ValueError:
                pass
                
        return (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
            .all()
        )


