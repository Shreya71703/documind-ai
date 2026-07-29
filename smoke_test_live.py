import urllib.request
import urllib.parse
import json

backend_url = "https://documind-backend-j6el.onrender.com"
frontend_origin = "https://documind-frontend-tgpv.onrender.com"

print("--- 1. Testing Health Endpoint ---")
try:
    req = urllib.request.Request(f"{backend_url}/health")
    with urllib.request.urlopen(req) as resp:
        print(f"Health status: {resp.status}, Body: {resp.read().decode()}")
except Exception as e:
    print(f"Health check failed: {e}")

print("\n--- 2. Testing Preflight OPTIONS (CORS Check) ---")
try:
    req = urllib.request.Request(
        f"{backend_url}/api/v1/auth/login",
        headers={
            "Origin": frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        method="OPTIONS"
    )
    with urllib.request.urlopen(req) as resp:
        print(f"OPTIONS status: {resp.status}")
        for k, v in resp.headers.items():
            if "access-control" in k.lower():
                print(f"  {k}: {v}")
except Exception as e:
    print(f"CORS Options check failed: {e}")

print("\n--- 3. Testing POST /api/v1/auth/register ---")
try:
    data = json.dumps({
        "email": "test_e2e_live@documind.ai",
        "password": "testpassword123",
        "full_name": "Test User"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{backend_url}/api/v1/auth/register",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": frontend_origin,
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Register status: {resp.status}, Body: {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"Register HTTP error: {e.code}, Body: {e.read().decode()}")
except Exception as e:
    print(f"Register failed: {e}")

print("\n--- 4. Testing POST /api/v1/auth/login ---")
try:
    data = json.dumps({
        "email": "test_e2e_live@documind.ai",
        "password": "testpassword123"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{backend_url}/api/v1/auth/login",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": frontend_origin,
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Login status: {resp.status}, Body: {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"Login HTTP error: {e.code}, Body: {e.read().decode()}")
except Exception as e:
    print(f"Login failed: {e}")
