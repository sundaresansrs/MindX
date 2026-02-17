import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.quality_pipeline import QualityPipeline
from app.models.user import User

# Mocking a user
class MockUser:
    def __init__(self, id, account_type):
        self.id = id
        self.account_type = account_type

async def test_pipeline():
    # Setup DB
    DATABASE_URL = "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    user = MockUser(id=1, account_type="personal") # Adjust if needed
    pipeline = QualityPipeline(db=db)
    
    print("Testing pipeline...")
    try:
        result = await pipeline.process_query(
            query="who is the founder of netflix",
            user=user,
            use_search=True,
            max_sources=10
        )
        print("Result successful!")
        print(f"Answer: {result.get('answer', 'NO ANSWER')[:100]}...")
    except Exception as e:
        import traceback
        print("PIPELINE FAILED!")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_pipeline())
