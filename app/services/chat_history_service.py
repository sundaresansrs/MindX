from sqlalchemy.orm import Session
from app.models.chat_history import ChatHistory


class ChatHistoryService:
    def __init__(self, db: Session):
        self.db = db

    def save(self, user_id: int, query: str, answer: str, source: str):
        record = ChatHistory(
            user_id=user_id,
            query=query,
            answer=answer,
            source=source,
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
