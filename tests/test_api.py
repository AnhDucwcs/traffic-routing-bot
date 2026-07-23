import time
from fastapi.testclient import TestClient
from app.main import app

# def test_health_check():
#     with TestClient(app) as client:
#         start_time = time.perf_counter()
#         for _ in range(5):
#             response = client.get("/health-check")
#             assert response.status_code == 200
#             assert response.json() == {"status": "healthy"}
#         end_time = time.perf_counter()
#     print(f"Health check endpoint responded in {end_time - start_time:.4f} seconds for 5 requests.")

def test_routing_endpoint_accepts_request():
    with TestClient(app) as client:
        payload = {
            "user_id": "test_user_001",
            "conversation_id": "conv_123",
            "platform": "java_app",
            "callbackUrl": "https://example.com/webhook",
            "origin": {"latitude": 10.762622, "longitude": 106.660172},
            "destination": {"latitude": 10.772622, "longitude": 106.670172}
        }
        
        # Test 403 Forbidden with WRONG API key
        resp_403 = client.post("/api/v1/routing/", json=payload, headers={"x-internal-api-key": "wrong_key"})
        assert resp_403.status_code == 403
        
        # Test 200 OK with correct schema and API key
        from app.core.config import settings
        headers = {"x-internal-api-key": settings.INTERNAL_API_KEY}
        resp = client.post("/api/v1/routing/", json=payload, headers=headers)
        if resp.status_code == 422:
            print("Validation error 200:", resp.json())
        assert resp.status_code == 200
        assert "tiếp nhận" in resp.json()["message"].lower()