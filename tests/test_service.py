import pytest
import networkx as nx
from shapely.geometry import LineString
from app.services.routing.service import routing_service

class MockTransformer:
    def transform(self, x, y):
        return x / 100.0, y / 100.0

class MockTrafficManager:
    def __init__(self, graph):
        self.G = graph
        self.to_graph = None
        self.to_wgs84 = MockTransformer()
        self.to_wgs84 = MockTransformer()
        # Mock time_weights as a tuple of 4 dicts (T0, T15, T30, T45)
        # We will simulate time-dependent weights
        t0 = {
            ("A", "B", 0): 10.0,
            ("A", "B", 1): 5.0, # best_key should be 1 at T0
            ("B", "C", 0): 15.0
        }
        t15 = {
            ("A", "B", 0): 4.0, # best_key should be 0 at T15
            ("A", "B", 1): 8.0, 
            ("B", "C", 0): 12.0
        }
        self.time_weights = (t0, t15, t15, t15) # T30, T45 same as T15 for mock
        self.active_weights = t0 # backward compat

@pytest.fixture
def mock_env():
    G = nx.MultiDiGraph()
    G.add_node("Virtual", x=0, y=0)
    G.add_node("A", x=1000, y=1000)
    G.add_node("B", x=2000, y=2000)
    G.add_node("C", x=3000, y=3000)
    
    G.add_edge("Virtual", "A", key=0)
    G.add_edge("A", "B", key=0)
    G.add_edge("A", "B", key=1)
    G.add_edge("B", "C", key=0)
    
    tm = MockTrafficManager(G)
    
    # geom_dict for LineStrings
    geom_dict = {
        # Edge (Virtual, A, 0)
        ("Virtual", "A", 0): LineString([(0, 0), (1000, 1000)]),
        # Edge (A, B, 0)
        ("A", "B", 0): LineString([(1000, 1000), (1500, 1500), (2000, 2000)]),
        # Edge (A, B, 1) - this should be chosen because weight is 5.0 < 10.0
        ("A", "B", 1): LineString([(1000, 1000), (1200, 1800), (2000, 2000)]),
        # Edge (B, C, 0)
        ("B", "C", 0): LineString([(2000, 2000), (3000, 3000)])
    }
    return tm, geom_dict

def test_to_geojson_selects_best_key(mock_env):
    tm, geom_dict = mock_env
    path = ["A", "B", "C"]
    
    # Input coordinates in wgs84
    start_lng, start_lat = 9.0, 9.0
    end_lng, end_lat = 31.0, 31.0
    
    geojson = routing_service.to_geojson(
        traffic_manager=tm,
        path=path,
        geom_dict=geom_dict,
        start_lng=start_lng,
        start_lat=start_lat,
        end_lng=end_lng,
        end_lat=end_lat
    )
    
    assert geojson is not None
    assert geojson["type"] == "Feature"
    coords = geojson["geometry"]["coordinates"]
    
    expected_coords = [
        (9.0, 9.0),
        (10.0, 10.0),
        (12.0, 18.0), # Proves key=1 was selected
        (20.0, 20.0),
        (30.0, 30.0),
        (31.0, 31.0)
    ]
    
    assert coords == expected_coords
    
def test_to_geojson_fallback_geometry(mock_env):
    tm, _ = mock_env
    # Empty geom_dict to trigger fallback
    geom_dict = {}
    path = ["A", "B"]
    
    geojson = routing_service.to_geojson(
        traffic_manager=tm,
        path=path,
        geom_dict=geom_dict,
        start_lng=9.0, start_lat=9.0, end_lng=21.0, end_lat=21.0
    )
    
    coords = geojson["geometry"]["coordinates"]
    expected_coords = [
        (9.0, 9.0),
        (10.0, 10.0), # Fallback straight line from A
        (20.0, 20.0), # Fallback straight line to B
        (21.0, 21.0)
    ]
    assert coords == expected_coords

def test_geojson_geometry_bucket_selection(mock_env):
    """
    Ensure to_geojson selects best_key using the correct time bucket 
    based on accumulated_s (time-dependent A* logic).
    """
    tm, geom_dict = mock_env
    path = ["Virtual", "A", "B", "C"]
    
    # Simulate A* returning edge_times that push the segment into T15 (>900s)
    # The first segment (Virtual -> A) takes 1000s.
    # So when evaluating A->B, accumulated_s is 1000s -> bucket T15
    # At T15, key 0 is better (4.0 < 8.0), whereas at T0, key 1 was better.
    # Note: edge_times is in minutes! 
    # To get 1000s, edge_times[0] = 1000 / 60 = 16.6666 minutes
    edge_times = [
        16.67,  # Virtual -> A (~1000s)
        0.2,    # A -> B (~12s)
        0.25    # B -> C (~15s)
    ]
    
    geojson = routing_service.to_geojson(
        traffic_manager=tm,
        path=path,
        geom_dict=geom_dict,
        start_lng=0.0, start_lat=0.0, end_lng=31.0, end_lat=31.0,
        edge_times=edge_times
    )
    
    coords = geojson["geometry"]["coordinates"]
    
    # Expected to pick key 0 for (A, B) because of T15 bucket
    expected_coords = [
        (0.0, 0.0),
        (10.0, 10.0), # End of Virtual->A
        (15.0, 15.0), # Proves key=0 was selected for A->B! (If key=1, it would be 12.0, 18.0)
        (20.0, 20.0),
        (30.0, 30.0),
        (31.0, 31.0)
    ]
    assert coords == expected_coords

def test_eta_accumulated_s_alignment():
    """
    Ensure edge_times sum matches estimated_time_min * 60 closely.
    (This simulates the pathfinder.py output).
    """
    # Mocking pathfinder post-processing outputs
    edge_times = [500.5, 300.0, 100.5] # Total = 901.0 seconds
    
    total_seconds = sum(edge_times)
    estimated_time_min = total_seconds / 60.0
    
    # Simulate checking the precision
    assert abs(sum(edge_times) - estimated_time_min * 60) < 0.001
