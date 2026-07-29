import os
import sys
import pytest

# Đảm bảo có thể import được các module từ app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.routing.map_builder import load_routing_graph, load_turn_penalties
from app.services.traffic_manager import TrafficManager

# =====================================================================
# FIXTURE: Nạp dữ liệu 1 lần duy nhất cho toàn bộ các Test Case
# =====================================================================
@pytest.fixture(scope="module")
def routing_components():
    print("\n[Fixture] Đang nạp Bản đồ và Turn Penalties vào RAM...")
    graph = load_routing_graph()
    turn_penalties = load_turn_penalties()
    traffic_manager = TrafficManager(graph, turn_penalties, edge_historical_baseline={}, id_to_edge=[], model=None)
    print("[Fixture] Khởi tạo xong TrafficManager!\n")
    return traffic_manager

def test_apply_crowdsourced_overrides(routing_components):
    """
    Kiểm tra chức năng override từ cộng đồng (Người dùng báo cáo kẹt xe).
    """
    traffic_manager = routing_components
    
    # Lấy 1 cạnh bất kỳ trong đồ thị làm ví dụ
    sample_edge = list(traffic_manager.G.edges(keys=True))[0]
    u, v, k = sample_edge
    
    # Ghi nhận thời gian gốc
    base_time = traffic_manager.bg_weights.get((u, v, k), 10.0)
    base_speed = traffic_manager.bg_speeds.get((u, v, k), 25.0)
    
    print(f"Base Time: {base_time}, Base Speed: {base_speed}")
    
    # Tạo báo cáo kẹt cứng (5 km/h)
    reports = [{
        "u": u,
        "v": v,
        "k": k,
        "speed_kmh": 5.0
    }]
    
    traffic_manager.apply_crowdsourced_overrides(reports)
    
    new_time = traffic_manager.bg_weights.get((u, v, k))
    new_speed = traffic_manager.bg_speeds.get((u, v, k))
    
    # Nếu tốc độ bị ép xuống 5km/h, thời gian đi qua cạnh sẽ phải tăng lên
    assert new_speed == 5.0, f"Expected speed 5.0, got {new_speed}"
    if 5.0 < base_speed:
        assert new_time > base_time, "Thời gian phải tăng lên do kẹt xe"
    
def test_crawler_speed_kmh_clamping(routing_components):
    """
    Kiểm tra chức năng validate đầu vào của crawler_speed_kmh
    Đảm bảo nó không bao giờ <= 0 (tránh ZeroDivisionError)
    """
    traffic_manager = routing_components
    
    # Lấy 1 cạnh bất kỳ trong đồ thị làm ví dụ
    sample_edge = list(traffic_manager.G.edges(keys=True))[0]
    u, v, k = sample_edge
    
    reports = [{
        "u": u,
        "v": v,
        "k": k,
        "speed_kmh": 0.0 # Tốc độ rác từ đầu vào
    }]
    
    traffic_manager.apply_crowdsourced_overrides(reports)
    
    new_speed = traffic_manager.bg_speeds.get((u, v, k))
    
    # Phải được clamp về 1.0 km/h
    assert new_speed == 1.0, f"Expected clamped speed 1.0, got {new_speed}"
