"""
Live diagnostic: Send a query and capture exactly what happens
"""
import asyncio
import httpx
import sys

async def test_with_logging():
    url = "http://localhost:8000/api/stream"
    
    # Login first
    login_data = {
        "username": "streamtest@example.com",
        "password": "TestPass123!"
    }
    
    print("🔐 Logging in...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                "http://localhost:8000/auth/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if resp.status_code != 200:
                print(f"❌ Login failed: {resp.status_code}")
                print(resp.text)
                return
            token = resp.json()["access_token"]
            print("✅ Logged in\n")
        except Exception as e:
            print(f"❌ Login error: {e}")
            return
        
        # Send query
        payload = {
            "query": "what is AI",
            "session_id": None,
            "use_search": True,
            "max_sources": 5,
            "fast_mode": False
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        
        print(f"📤 Sending query: '{payload['query']}'")
        print("⏱️  Waiting for response...\n")
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            async with client.stream("POST", url, json=payload, headers=headers, timeout=30.0) as response:
                print(f"📡 Got response status: {response.status_code}")
                
                if response.status_code != 200:
                    body = await response.aread()
                    print(f"❌ Error response: {body.decode()}")
                    return
                
                chunk_num = 0
                async for line in response.aiter_lines():
                    elapsed = asyncio.get_event_loop().time() - start_time
                    
                    if line.startswith("data: "):
                        chunk_num += 1
                        data = line[6:]
                        
                        if data == "[DONE]":
                            print(f"\n✅ Stream complete at {elapsed:.1f}s")
                            break
                        
                        # Parse and show chunk type
                        try:
                            import json
                            chunk_data = json.loads(data)
                            chunk_type = chunk_data.get("type", "unknown")
                            
                            if chunk_type == "status":
                                print(f"[{elapsed:.1f}s] 📊 STATUS: {chunk_data.get('content', '')}")
                            elif chunk_type == "token":
                                content = chunk_data.get("content", "")
                                print(f"[{elapsed:.1f}s] 💬 TOKEN: {content[:50]}", end="", flush=True)
                            elif chunk_type == "metadata":
                                print(f"\n[{elapsed:.1f}s] 📋 METADATA: {chunk_data.get('sources', []).__len__()} sources")
                            elif chunk_type == "error":
                                print(f"\n[{elapsed:.1f}s] ❌ ERROR: {chunk_data.get('content', '')}")
                                break
                        except:
                            print(f"[{elapsed:.1f}s] Chunk {chunk_num}: {data[:100]}")
                        
                        if chunk_num >= 20:
                            print("\n✅ Got 20+ chunks, stream is working!")
                            break
                
                if chunk_num == 0:
                    print(f"❌ NO DATA received after {elapsed:.1f}s")
                    
        except asyncio.TimeoutError:
            print("❌ TIMEOUT after 30 seconds - stream hung!")
        except Exception as e:
            print(f"❌ Stream error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_with_logging())
