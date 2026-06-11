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

def test_core_routing_state_machine():
    with TestClient(app) as client:
        # --- BƯỚC 1: GỬI ĐIỂM A ---
        payload_a = {
            "user_id": "test_user_001",
            "platform": "java_web",
            "latitude": 10.762622,
            "longitude": 106.660172
        }
        # Lưu ý: Thay "/api/v1/routing" bằng endpoint thực tế trong file routes.py của bạn
        response_a = client.post("/api/v1/routing", json=payload_a)
        
        # Kỳ vọng: API trả về 200 OK và một thông điệp yêu cầu gửi điểm B
        assert response_a.status_code == 200
        assert "vị trí đích" in response_a.json()["message"].lower() # Tùy chỉnh theo text bạn định trả về

        # --- BƯỚC 2: GỬI ĐIỂM B (CÙNG USER_ID) ---
        payload_b = {
            "user_id": "test_user_001", # Phải giống hệt ở trên để hệ thống nhận diện
            "platform": "java_web",
            "latitude": 10.772622, 
            "longitude": 106.670172
        }
        response_b = client.post("/api/v1/routing", json=payload_b)
        
        # Kỳ vọng: API nhận diện được session, tính toán, và trả về kết quả lộ trình
        assert response_b.status_code == 200
        assert "route found" in response_b.json()["message"].lower() # Tùy chỉnh theo cách bạn format JSON trả về