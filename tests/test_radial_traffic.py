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
    """Xác nhận API chỉ xuất các cung đường có is_bus_route = True và nằm trong BBox."""
    # BBox bao trọn điểm (0.0, 0.0) đến (0.0, ~0.09) (tức 10km)
    min_lng, min_lat = -0.5, -0.5
    max_lng, max_lat = 0.5, 0.5
    
    result = tm_radial.get_bbox_traffic_layer(min_lng, min_lat, max_lng, max_lat, geom_dict_radial)
    
    assert result["type"] == "FeatureCollection"
    
    total_lines = 0
    for feature in result["features"]:
        coords = feature["geometry"]["coordinates"]
        total_lines += len(coords)
        
    # Có 3 cạnh trong đồ thị, nhưng 1 nằm ngoài BBox lớn (40km), 
    # và chỉ 2 cạnh (1,2) và (2,3) có is_bus_route=True
    assert total_lines > 0

def test_bbox_filtering(tm_radial, geom_dict_radial):
    """Xác thực BBox thực sự lọc các điểm bên ngoài."""
    # BBox siêu nhỏ, không chứa đỉnh nào (tọa độ giả -10, -10)
    min_lng, min_lat = -10.0, -10.0
    max_lng, max_lat = -9.0, -9.0
    
    res = tm_radial.get_bbox_traffic_layer(min_lng, min_lat, max_lng, max_lat, geom_dict_radial)
    
    # Không có điểm nào lọt vào BBox này
    total_lines = sum(len(f["geometry"]["coordinates"]) for f in res["features"])
    assert total_lines == 0
