from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.sql import func  # type: ignore

from app.database import Base  # type: ignore


class ChatHistory(Base):
    __tablename__ = "chat_history"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), index=True, nullable=True)  # groups messages into threads

    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    preview = Column(Text, nullable=True)          # snippet for sidebar

    source = Column(String, nullable=True)          # web / vector / hybrid
    title = Column(String(120), nullable=True)       # auto-generated from first message
    message_count = Column(Integer, default=0)       # cached count for sidebar display

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_pinned = Column(Integer, default=0)  # 0 for false, 1 for true (SQLite friendly)
    version = Column(Integer, default=1)   # version number for this query in this session
    confidence = Column(Integer, nullable=True) # Confidence percentage
