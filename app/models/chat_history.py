from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class ChatHistory(Base):
    __tablename__ = "chat_history"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), index=True, nullable=True)  # groups messages into threads

    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    source = Column(String, nullable=True)          # web / vector / hybrid
    title = Column(String(120), nullable=True)       # auto-generated from first message
    message_count = Column(Integer, default=0)       # cached count for sidebar display

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
