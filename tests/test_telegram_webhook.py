from fastapi.testclient import TestClient
from app.main import app


def test_webhook_route_command():
    # 1. Cấu trúc JSON giả lập Telegram gửi lệnh /route
    mock_route_payload = {
        "update_id": 10000,
        "message": {
            "message_id": 1,
            "from": {"id": 123456789, "is_bot": False, "first_name": "Test User"},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1716000000,
            "text": "/route"
        }
    }
    
    with TestClient(app) as client:
        # 2. Bắn request vào endpoint hiện tại
        response = client.post("/webhook/telegram", json=mock_route_payload) # Thay bằng URL webhook thật của bạn
        
        # 3. Kiểm tra kết quả
        assert response.status_code == 200
        # Thêm các assert khác nếu webhook của bạn trả về data cụ thể

def test_webhook_location():
    # 1. Cấu trúc JSON giả lập Telegram gửi Tọa độ (Location)
    mock_location_payload = {
        "update_id": 10001,
        "message": {
            "message_id": 2,
            "from": {"id": 123456789, "is_bot": False, "first_name": "Test User"},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1716000005,
            "location": {
                "latitude": 10.762622,  # Ví dụ tọa độ TP.HCM
                "longitude": 106.660172
            }
        }
    }
    
    with TestClient(app) as client:
        response = client.post("/webhook/telegram", json=mock_location_payload)
        assert response.status_code == 200