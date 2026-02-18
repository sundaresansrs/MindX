"""
Migration script to add missing columns to the users table
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:mindx_password_2026@localhost:5432/mindx")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

print(f"Connecting to: {DATABASE_URL.split('@')[-1]}")

with engine.connect() as conn:
    # Check current schema
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users'
        ORDER BY ordinal_position;
    """))
    
    print("\n📋 Current 'users' table schema:")
    existing_columns = []
    for row in result:
        existing_columns.append(row[0])
        print(f"  - {row[0]}: {row[1]}")
    
    # Add missing columns
    columns_to_add = {
        'full_name': 'VARCHAR',
        'account_type': 'VARCHAR',
        'company_name': 'VARCHAR',
        'access_level': 'VARCHAR'
    }
    
    print("\n🔧 Adding missing columns...")
    for col_name, col_type in columns_to_add.items():
        if col_name not in existing_columns:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                conn.commit()
                print(f"  ✅ Added: {col_name}")
            except Exception as e:
                print(f"  ⚠️  {col_name}: {e}")
        else:
            print(f"  ⏭️  {col_name} already exists")
    
    # Verify final schema
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users'
        ORDER BY ordinal_position;
    """))
    
    print("\n✅ Final 'users' table schema:")
    for row in result:
        print(f"  - {row[0]}: {row[1]}")

print("\n🎉 Migration complete!")
