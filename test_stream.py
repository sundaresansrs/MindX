"""
Quick test to verify the streaming endpoint is working
"""
import asyncio
import httpx

async def test_stream():
    url = "http://localhost:8000/qa/stream"
    
    # Create a test user token (you'll need to login first or use an existing token)
    # For now, let's just test if the endpoint responds
    
    payload = {
        "query": "tell me about world war",
        "session_id": None,
        "use_search": True,
        "max_sources": 5,
        "fast_mode": False
    }
    
    print("🧪 Testing /qa/stream endpoint...")
    print(f"Query: {payload['query']}\n")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, let's try to signup/login to get a token
            signup_data = {
                "email": "streamtest@example.com",
                "password": "TestPass123!",
                "full_name": "Stream Test",
                "account_type": "personal"
            }
            
            try:
                resp = await client.post("http://localhost:8000/auth/signup", json=signup_data)
                if resp.status_code == 200:
                    token = resp.json()["access_token"]
                    print("✅ Got auth token")
                else:
                    # Try login instead
                    login_data = {
                        "username": "streamtest@example.com",
                        "password": "TestPass123!"
                    }
                    resp = await client.post(
                        "http://localhost:8000/auth/login",
                        data=login_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    token = resp.json()["access_token"]
                    print("✅ Logged in successfully")
            except Exception as e:
                print(f"❌ Auth failed: {e}")
                return
            
            # Now test the stream
            headers = {"Authorization": f"Bearer {token}"}
            
            print("\n📡 Starting stream...")
            chunk_count = 0
            
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    print(f"❌ Stream failed with status {response.status_code}")
                    print(await response.aread())
                    return
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk_count += 1
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            print("\n✅ Stream completed successfully")
                            break
                        print(f"Chunk {chunk_count}: {data[:100]}...")
                        
                        if chunk_count >= 5:  # Just show first 5 chunks
                            print("\n✅ Stream is working! (stopping early)")
                            break
            
            if chunk_count == 0:
                print("❌ No data received from stream")
            else:
                print(f"\n✅ Received {chunk_count} chunks")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_stream())
