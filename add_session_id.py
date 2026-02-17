import sys
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import engine

def migrate():
    print("Connecting to database to add session_id...")
    try:
        with engine.connect() as conn:
            # Check if column exists
            check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='chat_history' AND column_name='session_id';")
            result = conn.execute(check_sql).fetchone()
            
            if not result:
                print("Adding column session_id to chat_history...")
                conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_id UUID;"))
                conn.commit()
                print("Column added successfully.")
            else:
                print("Column session_id already exists.")
                
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
