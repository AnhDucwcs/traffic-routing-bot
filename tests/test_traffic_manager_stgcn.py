import pytest
import numpy as np
from app.services.routing.map_builder import (
    load_routing_graph,
    load_turn_penalties,
    load_edge_index,
    load_stgcn_model,
    load_historical_baseline
)
from app.services.traffic_manager import TrafficManager

@pytest.fixture(scope="module")
def traffic_manager():
    """
    Fixture nạp bản đồ và mô hình STGCN một lần duy nhất cho toàn bộ module.
    """
    print("\n--- [Fixture] Loading Graph and Model ---")
    G = load_routing_graph()
    turn_penalties = load_turn_penalties()
    id_to_edge, edge_index, edge_weight = load_edge_index()
    model = load_stgcn_model(edge_index, edge_weight)
    baseline = load_historical_baseline()
    
    manager = TrafficManager(G, turn_penalties, baseline, id_to_edge, model)
    yield manager
    print("\n--- [Fixture] Teardown ---")

def test_stgcn_prediction_integration(traffic_manager):
    """
    Kiểm thử sự tích hợp của STGCN vào trong TrafficManager.
    Giả lập đẩy dữ liệu vào buffer và bắt ép AI dự đoán.
    """
    manager = traffic_manager
    
    # 1. Đảm bảo mô hình AI đã được load thành công
    assert manager.ai_engine is not None, "Mô hình STGCN không được nạp (Có thể thiếu file .pth)"
    assert manager.id_to_edge is not None, "Thiếu id_to_edge"
    
    N = len(manager.id_to_edge)
    print(f"\nTổng số đường (N): {N}")
    
    # 2. Giả lập Buffer: Bơm 4 khung giờ tốc độ ngẫu nhiên từ 15km/h đến 40km/h
    for i in range(4):
        dummy_speeds = np.random.uniform(15.0, 40.0, N).astype(np.float32)
        manager.history_buffer.append((i, dummy_speeds))
        
    assert len(manager.history_buffer) == 4, "Buffer không chứa đủ 4 khung giờ"
    
    # 3. Kích hoạt Tiên tri (Bypass cơ chế cache thời gian)
    manager._cached_slot = -99
    manager.refresh_future_weights()
    
    # Trong môi trường thực tế, Crawler sẽ gọi hàm swap: 
    # self.time_weights = (self.bg_weights.copy(), *self._future_dicts)
    # Vì chúng ta chỉ gọi refresh, nên hãy lấy thẳng kết quả từ _future_dicts
    
    t0_dict = manager.bg_weights
    t15_dict = manager._future_dicts[0]
    t30_dict = manager._future_dicts[1]
    t45_dict = manager._future_dicts[2]
    
    assert isinstance(t0_dict, dict)
    assert isinstance(t15_dict, dict)
    
    assert len(t0_dict) == len(manager._base_weights), "T0 dictionary bị thiếu cạnh"
    assert len(t15_dict) == len(manager._base_weights), "T15 dictionary bị thiếu cạnh"
    
    # 5. Kiểm tra xem có sự thay đổi trên toàn cục không (thay vì soi 1 đường duy nhất)
    changed_count = 0
    for i in range(N):
        u, v, k = manager.id_to_edge[i]
        b_time = t0_dict[(u, v, k)]
        p_time = t15_dict[(u, v, k)]
        if abs(b_time - p_time) > 1e-4:  # Sai số float
            changed_count += 1
            if changed_count == 1:
                print(f"\n[Một đường bị ảnh hưởng bởi STGCN: ID={i} ({u}->{v})]")
                print(f"Base Time (T0):  {b_time:.2f} giây")
                print(f"Dự đoán (T15):   {p_time:.2f} giây")
    
    print(f"\nTổng số đường bị thay đổi trọng số bởi AI: {changed_count}/{N}")
    assert changed_count > 0, "Trọng số không hề thay đổi. AI chưa hoạt động hoặc predict ra toàn hằng số!"
