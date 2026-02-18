import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models.document import Document
from app.services.embeddings import EmbeddingsService

async def test_vector():
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        embed_service = EmbeddingsService()
        vec = embed_service.get_embeddings(["test"])[0]
        print(f"Vector length: {len(vec)}")
        
        # Robust string-based cast
        vec_str = "[" + ",".join(map(str, vec)) + "]"
        from sqlalchemy import text
        
        stmt = select(Document).order_by(
            text(f"embedding <=> '{vec_str}'::vector")
        ).limit(1)
        
        print("Executing search...")
        result = db.scalars(stmt).first()
        print(f"Found document: {result.id if result else 'None'}")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_vector())
