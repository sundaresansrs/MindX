from app.database import engine
from sqlalchemy import text

def update_schema():
    print("Checking/Updating schema for 'documents' table...")
    with engine.connect() as conn:
        try:
            # Check if column exists
            check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='documents' AND column_name='user_id'")
            res = conn.execute(check_sql).fetchone()
            
            if res:
                print("Column 'user_id' already exists.")
            else:
                print("Adding 'user_id' column...")
                alter_sql = text("ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES users(id)")
                conn.execute(alter_sql)
                conn.commit()
                print("Column 'user_id' added successfully.")
                
            # Double check
            res = conn.execute(check_sql).fetchone()
            print(f"Final check success: {res is not None}")
            
        except Exception as e:
            print(f"Error updating schema: {e}")

if __name__ == "__main__":
    update_schema()
