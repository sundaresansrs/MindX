import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def inspect_db():
    conn_str = os.getenv("DATABASE_URL")
    print(f"Connecting to: {conn_str}")
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    # List columns for users table
    try:
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users';")
        columns = cur.fetchall()
        print("\nColumns in 'users' table:")
        for col in columns:
            print(f" - {col[0]} ({col[1]})")
            
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'documents';")
        columns = cur.fetchall()
        print("\nColumns in 'documents' table:")
        for col in columns:
            print(f" - {col[0]} ({col[1]})")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    inspect_db()
