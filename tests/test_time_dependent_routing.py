import pytest
import networkx as nx
from app.services.traffic_manager import TrafficManager


@pytest.fixture(scope="module")
def mini_graph():
    """Đồ thị tí hon 4 nodes cho unit test. Không load file nặng."""
    G = nx.MultiDiGraph()
    # A -> B -> C -> D (đường thẳng, mỗi cạnh 500m)
    for u, v in [(1, 2), (2, 3), (3, 4)]:
        G.add_edge(u, v, key=0, length=500.0, base_time=40.0,
                   speed_kmh=45.0, highway='primary', is_bus_route=True)
        G.nodes[u]['x'], G.nodes[u]['y'] = 0.0, float(u)
        G.nodes[v]['x'], G.nodes[v]['y'] = 0.0, float(v)
        G.nodes[v]['traffic_signals'] = False
    G.nodes[1]['traffic_signals'] = False
    return G


@pytest.fixture(scope="module")
def tm(mini_graph):
    """TrafficManager với đồ thị tí hon, không load baseline file."""
    tm = TrafficManager(mini_graph, turn_penalties={}, edge_historical_baseline={}, id_to_edge=[], model=None)
    # Giả lập historical baseline: edge (1,2) kẹt cứng ở slot 30 (7h30)
    tm.edge_baseline = {
        (1, 2, 1, 30): 10.0,   # 10 km/h (kẹt xe)
        (1, 2, 1, 31): 12.0,   # 12 km/h (vẫn kẹt)
        (1, 2, 1, 32): 20.0,   # 20 km/h (đang giãn)
        (1, 2, 1, 33): 35.0,   # 35 km/h (thông thoáng)
    }
    return tm


def test_time_weights_is_tuple_of_4_dicts(tm):
    """time_weights phải là tuple chứa đúng 4 flat dict."""
    assert isinstance(tm.time_weights, tuple)
    assert len(tm.time_weights) == 4
    for d in tm.time_weights:
        assert isinstance(d, dict)


def test_base_time_fallback(tm):
    """Edge không có baseline phải trả về base_time."""
    t0 = tm.time_weights[0]
    assert t0[(2, 3, 0)] == 40.0  # base_time mặc định


def test_active_weights_backward_compat(tm):
    """Property active_weights phải trả về T0."""
    assert tm.active_weights is tm.time_weights[0]


def test_reset_restores_base_time(tm):
    """reset_traffic() phải đưa toàn bộ về base_time."""
    tm.reset_traffic()
    for d in tm.time_weights:
        assert d[(1, 2, 0)] == 40.0


def test_time_idx_formula():
    """Công thức chọn rổ thời gian: 900s = 15 phút."""
    assert min(int(0 // 900), 3) == 0      # 0s -> T0
    assert min(int(899 // 900), 3) == 0     # 14:59 -> T0
    assert min(int(900 // 900), 3) == 1     # 15:00 -> T15
    assert min(int(1800 // 900), 3) == 2    # 30:00 -> T30
    assert min(int(2700 // 900), 3) == 3    # 45:00 -> T45
    assert min(int(9999 // 900), 3) == 3    # >45 phút -> vẫn T45 (capped)


def test_night_mode_returns_base_time(tm):
    """Night mode (slot >= 86 or slot < 22) phải trả về base_time."""
    from app.services.traffic_manager import NIGHT_START_SLOT, NIGHT_END_SLOT
    # Slot 90 = 22h30 (Night mode)
    result = tm._build_future_dict(day_type=1, time_slot=90)
    assert result[(1, 2, 0)] == 40.0  # base_time, không bị historical override

    # Slot 10 = 02h30 (Night mode)
    result = tm._build_future_dict(day_type=1, time_slot=10)
    assert result[(1, 2, 0)] == 40.0


def test_historical_override_during_day(tm):
    """Slot trong giờ hoạt động phải dùng historical speed."""
    # Slot 30 = 7h30, edge (1,2) có baseline speed = 10 km/h
    result = tm._build_future_dict(day_type=1, time_slot=30)
    # speed 10 km/h, length 500m -> 500 / (10/3.6) = 180s
    expected = 500.0 / (10.0 / 3.6)  # ~180s
    assert abs(result[(1, 2, 0)] - expected) < 0.01
    # Edge (2,3) không có baseline -> giữ nguyên base_time
    assert result[(2, 3, 0)] == 40.0


def test_batch_apply_swaps_tuple(tm):
    """batch_apply_traffic_penalty phải swap time_weights thành tuple mới."""
    old_tuple = tm.time_weights
    tm.batch_apply_traffic_penalty([
        {"segment_id": "fake_seg", "speed_kmh": 15.0}
    ])
    # time_weights phải là object khác (tuple mới)
    assert tm.time_weights is not old_tuple
    assert len(tm.time_weights) == 4
