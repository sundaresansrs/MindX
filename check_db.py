import sqlite3
import json

def check():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    email = 'srsundar2005@gmail.com'
    cursor.execute("SELECT id FROM users WHERE email=?", (email,))
    user = cursor.fetchone()
    if not user:
        print(f"User {email} not found")
        return
    
    user_id = user['id']
    print(f"User ID: {user_id}")
    
    cursor.execute("SELECT COUNT(id) as cnt FROM chat_history WHERE user_id=?", (user_id,))
    total = cursor.fetchone()['cnt']
    print(f"Total messages for user: {total}")
    
    cursor.execute("""
        SELECT session_id, title, updated_at 
        FROM chat_history 
        WHERE user_id=? AND session_id IS NOT NULL 
        GROUP BY session_id 
        ORDER BY updated_at DESC
    """, (user_id,))
    sessions = [dict(r) for r in cursor.fetchall()]
    print(f"Found {len(sessions)} sessions")
    for s in sessions[:5]:
        print(f"  Session {s['session_id']}: {s['title']} ({s['updated_at']})")
    
    conn.close()

if __name__ == "__main__":
    check()
