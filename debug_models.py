import sys
import os

# Add path
sys.path.append(os.getcwd())

try:
    from app.database import engine, Base
    from app.models.document import Document
    print("Imported Document model.")
    
    # Try creating tables
    Base.metadata.create_all(bind=engine)
    print("SUCCESS: Tables created (or existed).")
except Exception as e:
    print(f"FAILURE: {e}")
