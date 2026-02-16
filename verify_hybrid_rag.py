import requests
import json
import time

BASE_URL = "http://localhost:8000"

def wait_for_server():
    for i in range(10):
        try:
            resp = requests.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

def test_ingest():
    print("Testing Ingest...")
    url = f"{BASE_URL}/documents/ingest"
    payload = {"text": "This is a test document for Hybrid RAG."}
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            print(f"SUCCESS: Ingested document. ID: {resp.json()['id']}")
            return True
        else:
            print(f"FAILURE: Ingest failed. {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_search():
    print("Testing Search...")
    url = f"{BASE_URL}/documents/search"
    payload = {"query": "test", "limit": 1}
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            results = resp.json()
            print(f"SUCCESS: Search returned {len(results)} results.")
            if results:
                print(f"First result: {results[0]['content']}")
            return True
        else:
            print(f"FAILURE: Search failed. {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    if wait_for_server():
        if test_ingest():
            test_search()
    else:
        print("Server did not start.")
