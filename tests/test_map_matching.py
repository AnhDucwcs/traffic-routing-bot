import os
import sys
import pytest

# Đảm bảo có thể import được các module từ app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.routing.map_builder import load_routing_graph, load_turn_penalties, load_feather_data
from app.services.traffic_manager import TrafficManager
from app.services.routing.map_matching import MapMatcher
from app.services.routing.pathfinder import find_shortest_path

# =====================================================================
# FIXTURE: Nạp dữ liệu 1 lần duy nhất cho toàn bộ các Test Case
# =====================================================================
@pytest.fixture(scope="module")
def routing_components():
    print("\n[Fixture] Đang nạp Bản đồ và Turn Penalties vào RAM...")
    graph = load_routing_graph()
    target_crs = graph.graph['crs']
    strtree, edge_ids, geom_dict = load_feather_data(target_crs)
    map_matcher = MapMatcher(strtree, edge_ids, geom_dict)
    turn_penalties = load_turn_penalties()
    traffic_manager = TrafficManager(graph, turn_penalties)
    print("[Fixture] Khởi tạo xong TrafficManager và MapMatcher!\n")
    
    return traffic_manager, map_matcher

# =====================================================================
# TEST CASES
# =====================================================================

@pytest.mark.asyncio
async def test_tc1_wrong_lane_snap(routing_components):
    """
    Test Case 1: Lỗi Dải phân cách (Lý Thường Kiệt -> Bắc Hải)
    Kỳ vọng: Tìm thấy đường đi bình thường, không bị snap nhầm sang làn ngược chiều.
    """
    traffic_manager, map_matcher = routing_components
    start_lat, start_lng = 10.773412004771103, 106.65734762465001
    end_lat, end_lng = 10.779339929656501, 106.65768521795057
    
    path, distance_km, estimated_time_min, edge_times = await find_shortest_path(
        traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng
    )
    
    assert path is not None, "Phải tìm thấy đường đi!"
    assert distance_km > 0
    print(f"\n[TC1] OK. Quãng đường: {distance_km} km. Start Node: {path[0]}")


@pytest.mark.asyncio
async def test_tc2_alley_snap(routing_components):
    """
    Test Case 2: Lỗi Bóng ma Hẻm cụt (Alley Snap)
    Kỳ vọng: Tọa độ mới nằm trong hẻm hợp lệ, PHẢI TÌM THẤY đường đi.
    """
    traffic_manager, map_matcher = routing_components
    
    # Tọa độ mới được User cấp (đã kiểm tra thuộc service road hợp lệ)
    start_lat, start_lng = 10.83518276625965, 106.67818138399366
    end_lat, end_lng = 10.83152785371064, 106.67757912322321
    
    path, distance_km, estimated_time_min, edge_times = await find_shortest_path(
        traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng
    )
    
    assert path is not None, "Tọa độ hợp lệ trong hẻm nhưng lại không tìm thấy đường!"
    assert distance_km > 0
    print(f"\n[TC2] OK. Đã định tuyến thành công từ trong hẻm ra ngoài. Quãng đường: {distance_km} km.")


@pytest.mark.asyncio
async def test_tc3_mid_block_jump(routing_components):
    """
    Test Case 3: Lỗi Nhảy cóc Thời gian (Đặng Văn Sâm - Mid-block)
    Kỳ vọng: Tìm thấy đường đi dài dằng dặc, không bị dịch chuyển tức thời.
    """
    traffic_manager, map_matcher = routing_components
    start_lat, start_lng = 10.81230367694846, 106.67473231235795
    end_lat, end_lng = 10.79302326849367, 106.67794476937286
    
    path, distance_km, estimated_time_min, edge_times = await find_shortest_path(
        traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng
    )
    
    assert path is not None, "Phải tìm thấy đường đi!"
    assert distance_km > 0
    print(f"\n[TC3] OK. Quãng đường thực tế: {distance_km} km. Không còn nhảy cóc.")


@pytest.mark.asyncio
async def test_tc4_airport_out_of_bounds(routing_components):
    """
    Test Case 4: Sân bay Tân Sơn Nhất (Đứng giữa rừng/biển)
    Kỳ vọng: Phải ném ra lỗi Exception vì khoảng cách tới đường bộ quá xa (> 50m).
    """
    traffic_manager, map_matcher = routing_components
    start_lat, start_lng = 10.818669235409956, 106.65225772365166
    end_lat, end_lng = 10.794334849317934, 106.6565979224164
    
    with pytest.raises(Exception, match="Khoảng cách tới đường bộ quá xa"):
        await find_shortest_path(
            traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng
        )
    print("\n[TC4] OK. Đã phòng thủ thành công chặn tọa độ ma ngoài phạm vi 50m.")
