from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models.user import User
from app.utils.security import hash_password
import time

def test_signup():
    db = SessionLocal()
    print("Testing DB User Creation...")
    try:
        email = f"test_manual_{int(time.time())}@example.com"
        pwd = "password123"
        print(f"Hashing password: '{pwd}' (len: {len(pwd)})")
        hashed = hash_password(pwd)
        print(f"Hashed password: '{hashed}' (len: {len(hashed)})")
        
        db_user = User(
            email=email,
            password_hash=hashed,
            account_type="personal",
            full_name="Manual Test"
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        print(f"User created successfully: {db_user.email}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_signup()
