import sys
import time
import requests

API_URL = "http://localhost:8000/api/v1"

def run_smoke_test():
    print("1. Registering temporary user...")
    email = f"smoke_test_{int(time.time())}@example.com"
    password = "StrongPassword123!"
    
    resp = requests.post(f"{API_URL}/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Smoke Test User"
    })
    if not resp.ok:
        print(f"Failed to register: {resp.text}")
        sys.exit(1)
    
    print("2. Logging in...")
    resp = requests.post(f"{API_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if not resp.ok:
        print(f"Failed to login: {resp.text}")
        sys.exit(1)
    
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print("3. Verifying /me...")
    resp = requests.get(f"{API_URL}/auth/me", headers=headers)
    if not resp.ok:
        print(f"Failed /me: {resp.text}")
        sys.exit(1)
        
    print("4. Uploading synthetic document...")
    files = {"file": ("smoke_doc.txt", "The capital of Aurora is NeoCity. It was founded in 2045 by Maya Verma.", "text/plain")}
    resp = requests.post(f"{API_URL}/documents/upload", headers=headers, files=files)
    if not resp.ok:
        print(f"Failed upload: {resp.text}")
        sys.exit(1)
        
    doc_id = resp.json()["id"]
    
    print(f"5. Triggering document processing for {doc_id}...")
    resp = requests.post(f"{API_URL}/documents/{doc_id}/process", headers=headers)
    if not resp.ok:
        print(f"Failed processing: {resp.text}")
        sys.exit(1)
        
    print("Waiting for processing to complete...")
    for _ in range(10):
        resp = requests.get(f"{API_URL}/documents", headers=headers)
        doc = next(d for d in resp.json() if d["id"] == doc_id)
        if doc["status"] == "ready":
            break
        time.sleep(1)
    
    if doc["status"] != "ready":
        print("Document failed to process.")
        sys.exit(1)
        
    print(f"6. Triggering document indexing for {doc_id}...")
    resp = requests.post(f"{API_URL}/documents/{doc_id}/index", headers=headers)
    if not resp.ok:
        print(f"Failed indexing: {resp.text}")
        sys.exit(1)
        
    print("Waiting for indexing to complete...")
    for _ in range(20):
        resp = requests.get(f"{API_URL}/documents", headers=headers)
        doc = next(d for d in resp.json() if d["id"] == doc_id)
        if doc["index_status"] == "indexed":
            break
        elif doc["index_status"] == "failed":
            print("Indexing failed.")
            sys.exit(1)
        time.sleep(1)
        
    if doc["index_status"] != "indexed":
        print("Document failed to index in time.")
        sys.exit(1)
        
    print("7. Creating chat session...")
    resp = requests.post(f"{API_URL}/chats", headers=headers, json={
        "title": "Smoke Test Chat",
        "document_ids": [doc_id]
    })
    if not resp.ok:
        print(f"Failed to create chat: {resp.text}")
        sys.exit(1)
        
    chat_id = resp.json()["id"]
    
    print("8. Asking grounded question...")
    resp = requests.post(f"{API_URL}/chats/{chat_id}/messages", headers=headers, json={
        "question": "Who founded NeoCity and when?"
    })
    
    if not resp.ok:
        print(f"Failed to ask question: {resp.text}")
        sys.exit(1)
        
    answer = resp.json()["content"]
    print(f"Answer: {answer}")
    
    print("9. Verifying grounded fact...")
    if "Maya Verma" not in answer or "2045" not in answer:
        print("Answer did not contain expected facts.")
        sys.exit(1)
        
    print("10. Verifying citations...")
    if "[SOURCE " not in answer:
        print("No citation tags found in answer.")
        sys.exit(1)
        
    print("11. Verifying chat persistence...")
    resp = requests.get(f"{API_URL}/chats/{chat_id}", headers=headers)
    if not resp.ok or len(resp.json().get("messages", [])) < 2:
        print("Chat history not persisted.")
        sys.exit(1)
        
    print("12. Cleaning up chat...")
    requests.delete(f"{API_URL}/chats/{chat_id}", headers=headers)
    
    print("13. Cleaning up document...")
    requests.delete(f"{API_URL}/documents/{doc_id}", headers=headers)
    
    print("Smoke test completed successfully!")

if __name__ == "__main__":
    run_smoke_test()
