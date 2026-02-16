from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# If it's a cloud database (like Supabase/Aiven), it often requires SSL
if DATABASE_URL and "postgresql" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

# Default to local if no URL provided (for safety)
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"

print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}") # Log host only for security
engine = create_engine(DATABASE_URL)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
