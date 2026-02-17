from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from pgvector.sqlalchemy import Vector
import uuid
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    content = Column(Text, nullable=False)
    source_url = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True) # Per-chat context
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    
    # Jina v2-base-en has 768 dimensions
    embedding = Column(Vector(768))

    def __repr__(self):
        return f"<Document id={self.id} source={self.source_url}>"
