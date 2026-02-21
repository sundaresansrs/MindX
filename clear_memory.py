from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user_memory import UserMemory

def clear_polluted_memory():
    db = SessionLocal()
    try:
        # Delete all existing memory entries to clear the hallucinated facts
        deleted_count = db.query(UserMemory).delete()
        db.commit()
        print(f"Successfully deleted {deleted_count} polluted memory entries.")
    except Exception as e:
        print(f"Error clearing memory: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clear_polluted_memory()
