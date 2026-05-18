import time
from fastapi.testclient import TestClient
from app.main import app

def test_health_check():
    with TestClient(app) as client:
        start_time = time.perf_counter()
        for _ in range(5):
            response = client.get("/health-check")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}
        end_time = time.perf_counter()
    print(f"Health check endpoint responded in {end_time - start_time:.4f} seconds for 5 requests.")