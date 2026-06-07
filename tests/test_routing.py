import pytest
import networkx as nx
import asyncio
import math
import threading

# --- 1. MOCK HÀM HEURISTIC VÀ LÕI TÌM ĐƯỜNG ---
def calc_time_from_euclidean(u, v, graph):
    x1, y1 = graph.nodes[u]['x'], graph.nodes[u]['y']
    x2, y2 = graph.nodes[v]['x'], graph.nodes[v]['y']
    h = math.hypot(x2 - x1, y2 - y1)
    return h / 12.5

async def find_route_mock(traffic_manager, start_node, end_node):
    """Bản sao thu nhỏ của hàm tìm đường trong hệ thống"""
    path = await asyncio.to_thread(
        nx.astar_path, 
        traffic_manager.G, 
        start_node, 
        end_node, 
        heuristic=lambda u, v: calc_time_from_euclidean(u, v, traffic_manager.G), 
        weight="current_weight"
    )
    return path

# --- 2. MOCK CLASS TRAFFIC MANAGER ---
class MockTrafficManager:
    """Phiên bản giả lập TrafficManager không cần đọc file JSON/PKL"""
    def __init__(self, graph):
        self.G = graph
        # Giả lập Index: Nhận diện đoạn A->B (key 0) là tuyến xe buýt
        self.segment_index = {"bus_segment_test": [("A", "B", 0)]}
        self.write_lock = threading.Lock()

    def apply_traffic_penalty(self, segment_id, penalty_factor):
        target_edges = self.segment_index.get(segment_id, [])
        with self.write_lock:
            for u, v, k in target_edges:
                base = self.G[u][v][k]['base_time']
                self.G[u][v][k]['current_weight'] = base * penalty_factor

# --- 3. FIXTURE KHỞI TẠO ĐỒ THỊ ---
@pytest.fixture
def traffic_env():
    G = nx.MultiDiGraph()
    
    # Tọa độ giả lập để Heuristic có thể tính toán (mét)
    G.add_node("A", x=0, y=0)
    G.add_node("B", x=1000, y=0)
    G.add_node("C", x=500, y=500)
    
    # Đường chính: Đi thẳng A -> B (Khoảng cách ngắn, 80 giây)
    G.add_edge("A", "B", key=0, length=1000, base_time=80.0, current_weight=80.0, is_bus_route=True)
    
    # Đường hẻm: Vòng qua A -> C -> B (Khoảng cách dài, tổng 160 giây)
    G.add_edge("A", "C", key=0, length=700, base_time=80.0, current_weight=80.0, is_bus_route=False)
    G.add_edge("C", "B", key=0, length=700, base_time=80.0, current_weight=80.0, is_bus_route=False)
    
    return MockTrafficManager(G)

# --- 4. KỊCH BẢN TEST CHÍNH ---
@pytest.mark.asyncio
async def test_dynamic_routing_avoids_traffic(traffic_env):
    # Bước 1: Kiểm tra lúc đường thông thoáng
    # AI phải chọn đường chính (80 giây < 160 giây)
    normal_path = await find_route_mock(traffic_env, "A", "B")
    assert normal_path == ["A", "B"], "Thất bại: Đường thông thoáng nhưng AI không đi đường thẳng."
    
    # Bước 2: Báo kẹt xe đứt ruột trên đại lộ (x10 thời gian)
    # Lúc này A->B tốn 800 giây
    traffic_env.apply_traffic_penalty("bus_segment_test", penalty_factor=10.0)
    
    # Bước 3: Tìm đường lại với cùng tọa độ
    # AI phải bẻ lái qua hẻm (160 giây < 800 giây)
    detour_path = await find_route_mock(traffic_env, "A", "B")
    assert detour_path == ["A", "C", "B"], "Thất bại: Đường kẹt cứng nhưng AI không chịu lách hẻm."