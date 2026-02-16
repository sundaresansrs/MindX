from app.utils.security import hash_password
import bcrypt

def debug_bcrypt():
    test_pwd = "password123"
    print(f"Testing password: {test_pwd} (len: {len(test_pwd)})")
    
    try:
        hashed = hash_password(test_pwd)
        print(f"Hashed: {hashed} (len: {len(hashed)})")
    except Exception as e:
        print(f"Hash Error: {e}")

    # Check bcrypt directly
    try:
        salt = bcrypt.gensalt()
        hashed_direct = bcrypt.hashpw(test_pwd.encode('utf-8'), salt)
        print(f"Bcrypt Direct: {hashed_direct}")
    except Exception as e:
        print(f"Bcrypt Direct Error: {e}")

if __name__ == "__main__":
    debug_bcrypt()
