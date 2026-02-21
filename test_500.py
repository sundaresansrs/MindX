import requests
import json

url = "http://localhost:8000/api/stream"
headers = {"Content-Type": "application/json"}
# Note: we need a valid token to bypass 401. Or we can just hit /health to check if server is running.
# Let's hit the endpoint to see what error it returns (even without token, it might return 500 if the app failed to load)
response = requests.post(url, json={"query": "test", "file_ids": ["123"]}, headers=headers)
print(response.status_code)
print(response.text)
