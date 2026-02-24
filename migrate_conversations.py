import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import DATABASE_URL
from app.models.chat_history import ChatHistory
from app.models.conversation import Conversation

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate():
    db = SessionLocal()
    try:
        # 1. Create conversations table if it doesn't exist (Base.metadata.create_all would normally do this)
        # But we'll do it explicitly here via alembic style or simple create
        print("Ensuring conversations table exists...")
        from app.database import Base
        Base.metadata.create_all(bind=engine)

        # 2. Check if chat_history has conversation_id column
        print("Checking chat_history schema...")
        with engine.connect() as conn:
            # Check for column existence
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='chat_history' AND column_name='conversation_id'"))
            if not result.fetchone():
                print("Adding conversation_id column to chat_history...")
                conn.execute(text("ALTER TABLE chat_history ADD COLUMN conversation_id UUID"))
                conn.commit()

        # 3. Migrate data
        print("Migrating data from chat_history to conversations...")
        # Get unique (user_id, session_id) pairs from chat_history
        # where session_id is NOT null
        records = db.query(ChatHistory.user_id, ChatHistory.session_id, ChatHistory.title).filter(ChatHistory.session_id.isnot(None)).distinct(ChatHistory.session_id).all()
        
        migrated_count = 0
        for user_id, session_id, title in records:
            # Check if conversation already exists
            existing = db.query(Conversation).filter(Conversation.id == session_id).first()
            if not existing:
                new_conv = Conversation(
                    id=session_id,
                    user_id=user_id,
                    title=title or "Untitled Conversation"
                )
                db.add(new_conv)
                migrated_count += 1
        
        db.commit()
        print(f"Created {migrated_count} new conversation records.")

        # 4. Update chat_history records to link back
        print("Linking messages to conversations...")
        with engine.connect() as conn:
            conn.execute(text("UPDATE chat_history SET conversation_id = session_id WHERE session_id IS NOT NULL"))
            conn.commit()
        
        print("Migration complete!")

    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
