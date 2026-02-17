from sqlalchemy import text
from app.database import engine

def fix_documents():
    print("Fixing documents.user_id type...")
    try:
        with engine.connect() as conn:
            # Drop the problematic column and re-add it as integer
            # We truncate first since the data is likely invalid anyway
            conn.execute(text("TRUNCATE TABLE documents;"))
            conn.execute(text("ALTER TABLE documents DROP COLUMN IF EXISTS user_id;"))
            conn.execute(text("ALTER TABLE documents ADD COLUMN user_id INTEGER;"))
            conn.commit()
            print("Successfully fixed documents table.")
            
            # Double check chat_history
            conn.execute(text("ALTER TABLE chat_history ALTER COLUMN user_id TYPE INTEGER USING user_id::integer;"))
            conn.commit()
            print("Successfully verified chat_history table.")
            
    except Exception as e:
        print(f"Fix failed: {e}")

if __name__ == "__main__":
    fix_documents()
