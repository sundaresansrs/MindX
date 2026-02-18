
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

URL = "http://localhost:8000/qa/stream"
TOKEN_URL = "http://localhost:8000/auth/token"

# Use test user credentials or env
USERNAME = "testuser"
PASSWORD = "testpassword"

def get_token():
    # Login first
    try:
        data = {"username": USERNAME, "password": PASSWORD}
        resp = requests.post(TOKEN_URL, data=data) 
        if resp.status_code == 200:
            return resp.json()["access_token"]
        # Try creating user if not exists
        resp = requests.post("http://localhost:8000/auth/signup", json={"email": USERNAME, "password": PASSWORD})
        if resp.status_code == 200 or resp.status_code == 400:
             # Login again
             data = {"username": USERNAME, "password": PASSWORD}
             resp = requests.post(TOKEN_URL, data=data)
             return resp.json()["access_token"]
    except Exception as e:
        print(f"Auth failed: {e}")
        return None

token = get_token()
if not token:
    print("Could not get token, maybe server down or DB empty?")
    exit(1)

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
payload = {
    "query": "Who is Linus Torvalds?",
    "session_id": "test-session",
    "use_search": True,
    "max_sources": 5,
    "fast_mode": False
}

print(f"Sending request to {URL}...")
try:
    with requests.post(URL, json=payload, headers=headers, stream=True) as r:
        print(f"Status Code: {r.status_code}")
        if r.status_code != 200:
            print(f"Error Content: {r.text}")
        else:
            for line in r.iter_lines():
                if line:
                    print(line.decode('utf-8'))
except Exception as e:
    print(f"Request failed: {e}")
