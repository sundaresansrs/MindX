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
    # The database seems to be postgres as per app/database.py
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get a real user from DB if possible
        user = db.query(User).first()
        if not user:
            print("No user found in DB, creating mock user...")
            user = MockUser(id=1, account_type="personal")
            
        pipeline = QualityPipeline(db=db)
        
        print(f"Testing pipeline for user: {user.id}")
        result = await pipeline.process_query(
            query="What is photosynthesis?",
            user=user,
            use_search=True,
            max_sources=5
        )
        print("Result successful!")
        print(f"Answer: {result.get('answer', 'NO ANSWER')[:200]}...")
    except Exception as e:
        import traceback
        print("\n❌ PIPELINE FAILED!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_pipeline())
