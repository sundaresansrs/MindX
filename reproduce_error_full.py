import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.personal_pipeline import PersonalPipeline
from app.models.user import User

# Mocking a user
class MockUser:
    def __init__(self, id, account_type):
        self.id = id
        self.account_type = account_type

async def test_search():
    # Setup DB
    DATABASE_URL = "postgresql://postgres:mindx_password_2026@localhost:5432/mindx"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    # Try to find user with ID 1
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = MockUser(id=1, account_type="personal")
    
    pipeline = PersonalPipeline(db=db, user=user)
    
    print("Testing PersonalPipeline.search with 'Founder of Zepto'...")
    try:
        # Use a real-looking session_id
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        result = await pipeline.search(
            query="who is the founder of zepto",
            session_id=session_id,
            use_search=True,
            max_sources=10
        )
        print("Search successful!")
        print(f"Answer: {result.get('answer', 'NO ANSWER')[:200]}...")
    except Exception as e:
        import traceback
        print("SEARCH FAILED!")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_search())
