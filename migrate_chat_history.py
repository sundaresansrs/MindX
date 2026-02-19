from app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    columns_to_add = [
        ("is_pinned", "INTEGER DEFAULT 0"),
        ("version", "INTEGER DEFAULT 1"),
        ("confidence", "INTEGER"),
        ("title", "VARCHAR(120)"),
        ("message_count", "INTEGER DEFAULT 0"),
        ("source", "VARCHAR")
    ]
    
    with engine.connect() as conn:
        for col_name, col_type in columns_to_add:
            try:
                # Check if column exists
                check_sql = text(f"SELECT column_name FROM information_schema.columns WHERE table_name='chat_history' AND column_name='{col_name}'")
                res = conn.execute(check_sql).fetchone()
                
                if res:
                    logger.info(f"Column '{col_name}' already exists in 'chat_history'.")
                else:
                    logger.info(f"Adding '{col_name}' column to 'chat_history'...")
                    alter_sql = text(f"ALTER TABLE chat_history ADD COLUMN {col_name} {col_type}")
                    conn.execute(alter_sql)
                    conn.commit()
                    logger.info(f"Column '{col_name}' added successfully.")
            except Exception as e:
                logger.error(f"Error adding column '{col_name}': {e}")
                conn.rollback()

if __name__ == "__main__":
    migrate()
