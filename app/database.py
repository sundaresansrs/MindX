from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import logging

logger = logging.getLogger(__name__)


DATABASE_URL = os.getenv("DATABASE_URL")

# Production check: If we're on Vercel, DATABASE_URL MUST be set
IS_VERCEL = os.getenv("VERCEL") == "1"

if not DATABASE_URL:
    if IS_VERCEL:
        logger.error("CRITICAL: DATABASE_URL environment variable is not set!")
        # We'll use a placeholder that will cause a clear error on first query
        DATABASE_URL = "postgresql://MISSING_ENV_VAR@localhost/error"
    else:
        # Default to local only if NOT on Vercel
        DATABASE_URL = "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"

# SQLAlchemy 1.4+ requires 'postgresql://' instead of 'postgres://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure SSL for cloud databases (Supabase, Vercel Postgres, Neon)
if "localhost" not in DATABASE_URL and "sslmode" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{separator}sslmode=require"

print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")
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
