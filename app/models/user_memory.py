from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime  # type: ignore
from sqlalchemy.sql import func  # type: ignore
from app.database import Base  # type: ignore

class UserMemory(Base):
    __tablename__ = "user_memory"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    key = Column(String(100), nullable=False) # e.g. "programming_language", "pet_name"
    value = Column(Text, nullable=False)
    category = Column(String(50), nullable=True, default="general") # e.g. "pref", "fact", "work"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
