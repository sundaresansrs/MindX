from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    source = Column(String, nullable=True)  # web / vector / hybrid
    created_at = Column(DateTime(timezone=True), server_default=func.now())
