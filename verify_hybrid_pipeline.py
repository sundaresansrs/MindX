import httpx
import time

BASE_URL = "http://localhost:8000"

def get_token():
    print("Registering test user...")
    email = f"test_{int(time.time())}@example.com"
    payload = {
        "email": email, 
        "full_name": "Test User", 
        "password": "password123",
        "account_type": "personal"
    }
    with httpx.Client() as client:
        s_resp = client.post(f"{BASE_URL}/auth/signup", json=payload)
        print(f"Signup response: {s_resp.status_code} - {s_resp.text}")
    
    print("Logging in to get token...")
    with httpx.Client() as client:
        resp = client.post(f"{BASE_URL}/auth/login", data={"username": email, "password": "password123"})
        print(f"Login response: {resp.status_code} - {resp.text}")
    if resp.status_code == 200:
        return resp.json()["access_token"]



    print(f"Login failed: {resp.text}")
    return None

def test_hybrid_flow():
    token = get_token()
    if not token: return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Ingest a uniquely identifiable document
    print("Ingesting test document...")
    ingest_payload = {
        "text": "The secret code for MindX is ALPHA-DELTA-NINER. This information is only available in the local vector store.",
        "url": "internal://test-doc"
    }
    with httpx.Client() as client:
        client.post(f"{BASE_URL}/documents/ingest", json=ingest_payload)
    
    # Wait for DB commit/reload
    time.sleep(1)
    
    # 2. Query via QA endpoint
    print("Querying QA pipeline...")
    qa_payload = {
        "query": "What is the secret code for MindX?",
        "use_search": True
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{BASE_URL}/qa/search", json=qa_payload, headers=headers)
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"Answer: {result['answer']}")
        metadata = result.get("metadata", {})
        print(f"Web Sources: {metadata.get('web_sources')}")
        print(f"Vector Sources: {metadata.get('vector_sources')}")
        
        if metadata.get('vector_sources', 0) > 0:
            print("SUCCESS: Hybrid RAG retrieved local document!")
        else:
            print("FAILURE: Hybrid RAG did not retrieve local document.")
    else:
        print(f"QA Failed: {resp.status_code} - {resp.text}")
        with open("verification_result.txt", "w") as f:
            f.write(resp.text)

if __name__ == "__main__":
    test_hybrid_flow()
