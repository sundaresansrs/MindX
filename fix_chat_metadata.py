import os
import sys
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import DATABASE_URL
from app.models.chat_history import ChatHistory
from app.models.conversation import Conversation

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def fix_metadata():
    db = SessionLocal()
    try:
        print("Starting metadata correction...")
        
        conversations = db.query(Conversation).all()
        fixed_titles = 0
        fixed_dates = 0
        
        for conv in conversations:
            # Get messages for this conversation
            messages = db.query(ChatHistory).filter(ChatHistory.conversation_id == conv.id).order_by(ChatHistory.created_at.asc()).all()
            
            if not messages:
                print(f"Skipping empty conversation: {conv.id}")
                continue
                
            # 1. Fix Title
            if not conv.title or conv.title == "Untitled Conversation":
                # Try to get first message's query or title
                first_msg = messages[0]
                new_title = first_msg.title or first_msg.query[:100]
                if new_title:
                    conv.title = new_title
                    fixed_titles += 1
            
            # 2. Fix Dates
            # Start date is the earliest message
            # Update date is the latest message
            created_at = messages[0].created_at
            updated_at = messages[-1].created_at # Or updated_at if available in ChatHistory
            
            if created_at:
                conv.created_at = created_at
            if updated_at:
                conv.updated_at = updated_at
                
            fixed_dates += 1
            
        db.commit()
        print(f"Finished! Updated titles for {fixed_titles} chats and refined dates for {fixed_dates} chats.")

    except Exception as e:
        print(f"Fix failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_metadata()
