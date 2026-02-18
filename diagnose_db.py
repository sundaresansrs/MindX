import os
import sqlalchemy
from sqlalchemy import text
from dotenv import load_dotenv
load_dotenv()

def diagnose_db():
    url = os.getenv('DATABASE_URL') or 'postgresql://postgres:mindx_password_2026@localhost:5432/mindx'
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    engine = sqlalchemy.create_engine(url)
    with engine.connect() as conn:
        print("--- Extension Check ---")
        res = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'")).first()
        print(f"Vector extension: {res}")
        
        print("\n--- Operator Check ---")
        try:
            res = conn.execute(text("SELECT oprname, oprleft::regtype, oprright::regtype, oprresult::regtype FROM pg_operator WHERE oprname = '<=>' AND oprleft = 'vector'::regtype")).all()
            for r in res:
                print(f"Operator: {r}")
        except Exception as e:
            print(f"Operator check failed: {e}")
            
        print("\n--- Table Check ---")
        res = conn.execute(text("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'documents'")).all()
        for r in res:
            print(f"Column: {r}")

if __name__ == "__main__":
    diagnose_db()
