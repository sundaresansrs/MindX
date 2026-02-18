"""
Test script to verify signup and login endpoints
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("🧪 Testing Auth Endpoints\n")

# Test 1: Signup
print("1️⃣ Testing Signup...")
signup_data = {
    "email": "testuser123@example.com",
    "password": "SecurePass123!",
    "full_name": "Test User",
    "account_type": "personal"
}

try:
    response = requests.post(f"{BASE_URL}/auth/signup", json=signup_data)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Signup successful!")
        print(f"   Token: {data['access_token'][:20]}...")
        token = data['access_token']
    else:
        print(f"   ❌ Signup failed: {response.text}")
        token = None
except Exception as e:
    print(f"   ❌ Error: {e}")
    token = None

# Test 2: Login
print("\n2️⃣ Testing Login...")
login_data = {
    "username": "testuser123@example.com",  # OAuth2 uses 'username' field
    "password": "SecurePass123!"
}

try:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data=login_data,  # OAuth2 uses form data, not JSON
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Login successful!")
        print(f"   Token: {data['access_token'][:20]}...")
    else:
        print(f"   ❌ Login failed: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Get current user (if we have a token)
if token:
    print("\n3️⃣ Testing /auth/me endpoint...")
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            user_data = response.json()
            print(f"   ✅ User data retrieved!")
            print(f"   Email: {user_data.get('email')}")
            print(f"   Name: {user_data.get('full_name')}")
            print(f"   Type: {user_data.get('account_type')}")
        else:
            print(f"   ❌ Failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

print("\n✅ Auth endpoint testing complete!")
