import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate_db():
    conn_str = os.getenv("DATABASE_URL")
    print(f"Migrating: {conn_str}")
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    try:
        # 1. Add missing columns to users
        print("Updating 'users' table...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS account_type VARCHAR;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name VARCHAR;")
        
        # 2. Add missing columns to chat_history
        print("Updating 'chat_history' table...")
        cur.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS source VARCHAR;")
        
        conn.commit()
        print("Migration successful!")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migrate_db()
