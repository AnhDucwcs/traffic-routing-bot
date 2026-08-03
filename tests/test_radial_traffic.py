import pytest
import networkx as nx
import shapely.geometry as geom
from app.services.traffic_manager import TrafficManager

@pytest.fixture(scope="module")
def mini_graph_radial():
    """Đồ thị tí hon 4 nodes cho test Radial Traffic Layer."""
    G = nx.MultiDiGraph()
    G.graph['crs'] = 'EPSG:3857'  # Metric CRS for map matching / distances
    
    # A(0,0) -> B(0, 10km) -> C(0, 20km) -> D(0, 40km)
    nodes = {
        1: (0.0, 0.0),
        2: (0.0, 10000.0),
        3: (0.0, 20000.0),
        4: (0.0, 40000.0)
    }
    
    for u, (x, y) in nodes.items():
        G.add_node(u, x=x, y=y, traffic_signals=False)
        
    # Thêm cạnh với base speed khác nhau để test color
    edges_data = [
        (1, 2, 0, 10000.0, 45.0, True),   # 10km, base=45km/h, is_bus=True
        (2, 3, 0, 10000.0, 50.0, True),   # 10km, base=50km/h, is_bus=True
        (3, 4, 0, 20000.0, 60.0, False)   # 20km, base=60km/h, is_bus=False
    ]
    
    for u, v, key, length, speed, bus in edges_data:
        base_time = (length / (speed / 3.6))
        G.add_edge(u, v, key=key, length=length, base_time=base_time,
                   speed_kmh=speed, highway='primary', is_bus_route=bus)
                   
    return G

@pytest.fixture(scope="module")
def tm_radial(mini_graph_radial):
    """TrafficManager với đồ thị tí hon."""
    tm = TrafficManager(mini_graph_radial, turn_penalties={}, edge_historical_baseline={}, id_to_edge=[], model=None)
    
    # Thiết lập time_weights cho các xô khác nhau
    # T0 (hiện tại), T15 (sau 15p), T30 (sau 30p), T45 (sau 45p)
    t0 = tm.time_weights[0]
    t15 = tm.time_weights[1]
    t30 = tm.time_weights[2]
    t45 = tm.time_weights[3]
    
    # Edge (1, 2) có is_bus=True. Giả lập kẹt cứng ở T0 (10km/h), thông thoảng ở T15 (45km/h)
    length12 = mini_graph_radial[1][2][0]['length']
    t0[(1, 2, 0)] = length12 / (10.0 / 3.6) # Kẹt xe -> Red/Orange
    t15[(1, 2, 0)] = length12 / (45.0 / 3.6) # Thông thoáng -> Green
    
    # Edge (2, 3) có is_bus=True. Kẹt ở T30 (15km/h), bình thường ở T0 (50km/h)
    length23 = mini_graph_radial[2][3][0]['length']
    t0[(2, 3, 0)] = length23 / (50.0 / 3.6)
    t30[(2, 3, 0)] = length23 / (15.0 / 3.6)
    
    return tm

@pytest.fixture(scope="module")
def geom_dict_radial():
    """Từ điển hình học giả lập."""
    return {
        (1, 2, 0): geom.LineString([(0, 0), (0, 10000)]),
        (2, 3, 0): geom.LineString([(0, 10000), (0, 20000)]),
        (3, 4, 0): geom.LineString([(0, 20000), (0, 40000)])
    }

def test_bus_edge_filtering(tm_radial, geom_dict_radial):
    """Xác nhận API chỉ xuất các cung đường có is_bus_route = True."""
    # Lấy tọa độ tại xích đạo (0, 0)
    result = tm_radial.get_radial_traffic_layer(0.0, 0.0, geom_dict_radial)
    
    assert result["type"] == "FeatureCollection"
    
    total_lines = 0
    for feature in result["features"]:
        coords = feature["geometry"]["coordinates"]
        total_lines += len(coords)
        
    # Có 3 cạnh trong đồ thị, nhưng chỉ 2 cạnh (1,2) và (2,3) có is_bus_route=True
    assert total_lines == 2

def test_haversine_distance_time_bucket(tm_radial, geom_dict_radial):
    """
    Xác thực logic time_idx = min(int((t + 300) // 900), 3) hoạt động đúng.
    Người dùng ở (0, 0) (Kinh độ/Vĩ độ).
    Với to_wgs84: giả sử (0, 10000) đổi thành (0, ~0.09) độ vĩ.
    Ta sẽ dùng tọa độ user_lat, user_lng thay đổi để test các xô thời gian.
    """
    # Giao điểm V của (1, 2) là (0, 10000)
    # Giao điểm V của (2, 3) là (0, 20000)
    
    # 1. User đứng rất gần đích (khoảng cách 0m) -> time_idx = 0
    # Tính tọa độ wgs84 thực tế của điểm V(1, 2)
    v_x, v_y = tm_radial.G.nodes[2]['x'], tm_radial.G.nodes[2]['y']
    lng_v, lat_v = tm_radial.to_wgs84.transform(v_x, v_y)
    
    # Lấy layer với user đứng đúng tại lat_v, lng_v
    res_t0 = tm_radial.get_radial_traffic_layer(lat_v, lng_v, geom_dict_radial)
    
    # (1, 2) ở T0 kẹt cứng (10km/h vs 45km/h base) -> Ratio 0.22 -> Red
    # (2, 3) ở T0 bình thường (50km/h vs 50km/h base) -> Ratio 1.0 -> Green
    colors = {f["properties"]["color"]: len(f["geometry"]["coordinates"]) for f in res_t0["features"]}
    assert colors.get("red", 0) == 1
    assert colors.get("green", 0) == 1
    
    # 2. User đứng xa điểm (2, 3) khoảng 30 phút đi xe (tức ~15km, tính d = 15000m)
    # Tốc độ giả định = 8.33 m/s. t = 15000 / 8.33 = 1800s. 
    # (1800 + 300) // 900 = 2 -> T30
    
    # Để user cách lat_v (của 3) đúng 15km, ta dùng thủ thuật set_lat
    v3_x, v3_y = tm_radial.G.nodes[3]['x'], tm_radial.G.nodes[3]['y']
    lng_v3, lat_v3 = tm_radial.to_wgs84.transform(v3_x, v3_y)
    
    # Một độ vĩ tương đương ~111km, vậy 15km là ~0.135 độ
    user_lat_far = lat_v3 - 0.135
    user_lng_far = lng_v3
    
    res_t30 = tm_radial.get_radial_traffic_layer(user_lat_far, user_lng_far, geom_dict_radial)
    
    # (2, 3) ở T30 bị kẹt (15km/h vs 50km/h base) -> Ratio 0.3 -> Orange/Yellow
    colors_t30 = {f["properties"]["color"]: len(f["geometry"]["coordinates"]) for f in res_t30["features"]}
    assert colors_t30.get("orange", 0) == 1 or colors_t30.get("yellow", 0) == 1
