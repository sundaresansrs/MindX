from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    full_name = Column(String, nullable=True)
    account_type = Column(String, nullable=True)
    company_name = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
