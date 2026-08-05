import networkx as nx
import asyncio
import math
import heapq
import itertools
from pyproj import Transformer
from app.core.logger import logger

WAYPOINT_ANGLE_THRESHOLD: float = 25.0


def calc_time_from_point_to_node(p: tuple, node_id: int, graph) -> float:
    """
    Tính thời gian đi từ một điểm P' (tọa độ UTM: x, y) tới một Node trong đồ thị.
    - p: tuple (x, y) tính bằng mét.
    - Trả về: Thời gian (giây).
    """
    p_x, p_y = p
    node_x = graph.nodes[node_id]['x']
    node_y = graph.nodes[node_id]['y']
    h = math.hypot(p_x - node_x, p_y - node_y)
    t = h / 10 # Tốc độ heuristic là 36km/h
    return t

def custom_astar_path(traffic_manager, start_edge: tuple, p_start: tuple, end_edge: tuple, p_end: tuple, heuristic_func):
    """
    Thuật toán A* tùy chỉnh, hỗ trợ phạt góc rẽ và dùng Min-Heap (O(log N))
    start_edge: (start_u, start_v)
    p_start: Tọa độ Point rơi P' ở điểm xuất phát
    end_edge: (end_u, end_v)
    p_end: Tọa độ Point rơi P' ở điểm đích
    """
    c = itertools.count()
    open_set = []
    g_score = {}
    came_from = {}
    
    # Khởi tạo tập hợp điểm đích
    end_u, end_v = end_edge
    # Đường 1 chiều từ end_u đến end_v (Mặc định để đến được p_end thì luôn phải đi qua end_u)
    valid_targets = {end_u}
    # Đường 2 chiều
    if traffic_manager.G.has_edge(end_v, end_u):
        valid_targets.add(end_v)
    
    # Khởi tạo tập hợp điểm xuất phát
    start_u, start_v = start_edge
    # Đường 1 chiều từ start_u đến start_v
    time_to_v = calc_time_from_point_to_node(p_start, start_v, traffic_manager.G)
    heapq.heappush(open_set, (time_to_v + heuristic_func(p_end, start_v), next(c), start_v, start_u, time_to_v))
    g_score[(start_v, start_u)] = time_to_v
    # Nếu có đường 2 chiều, thêm start_u vào tập hợp điểm xuất phát
    if traffic_manager.G.has_edge(start_v, start_u):
        time_to_u = calc_time_from_point_to_node(p_start, start_u, traffic_manager.G)
        heapq.heappush(open_set, (time_to_u + heuristic_func(p_end, start_u), next(c), start_u, start_v, time_to_u))
        g_score[(start_u, start_v)] = time_to_u

    max_expansions = 60000
    expansions = 0

    while open_set:
        expansions += 1
        if expansions > max_expansions:
            raise nx.NetworkXNoPath(f"Đã vượt quá giới hạn tìm kiếm ({max_expansions} nodes). Có thể điểm đến bị cô lập.")
            
        f, _, current, prev_node, current_g = heapq.heappop(open_set)
        
        if current in valid_targets:
            path = [current]
            curr_state = (current, prev_node)
            while curr_state in came_from:
                curr_state = came_from[curr_state]
                if curr_state[0] is not None:
                    path.append(curr_state[0])
            path.reverse()
            final_segment_time = current_g + calc_time_from_point_to_node(p_end, current, traffic_manager.G)
            return path, final_segment_time
        
        # Nếu nhánh hiện tại có chi phí đắt hơn nhánh đã khám phá, bỏ qua
        if current_g > g_score.get((current, prev_node), float('inf')):
            continue
            
        for neighbor in traffic_manager.G.successors(current):
            edges = traffic_manager.G[current][neighbor]
            # ponytail: Chọn rổ thời gian dựa trên g_score tích lũy (900s = 15 phút)
            time_idx = min(int(current_g // 900), 3)
            tw = traffic_manager.time_weights[time_idx]
            # ponytail: Tối ưu vòng lặp (99% đường chỉ có 1 key là 0)
            if len(edges) == 1:
                travel_time = tw.get((current, neighbor, 0), 10.0)
            else:
                travel_time = min(tw.get((current, neighbor, k), 10.0) for k in edges)
            
            # GỌI HÀM PHẠT GÓC RẼ
            turn_penalty = traffic_manager.turn_penalties.get((prev_node, current, neighbor), 0.0)
                          
            # Ép xung A* với Bounded Suboptimal (Epsilon = 1.12)
            h_val = heuristic_func(p_end, neighbor) * 1.12
            
            tentative_g = current_g + travel_time + turn_penalty
            
            if tentative_g < g_score.get((neighbor, current), float('inf')):
                g_score[(neighbor, current)] = tentative_g
                f_score = tentative_g + h_val
                came_from[(neighbor, current)] = (current, prev_node)
                heapq.heappush(open_set, (f_score, next(c), neighbor, current, tentative_g))
                
    raise nx.NetworkXNoPath(f"Không tìm thấy đường từ {p_start} đến {p_end}")

async def find_shortest_path(traffic_manager, map_matcher, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    to_graph, to_wgs84 = traffic_manager.to_graph, traffic_manager.to_wgs84

    if to_graph:
        start_x, start_y = to_graph.transform(start_lng, start_lat)
        end_x, end_y = to_graph.transform(end_lng, end_lat)
    else:
        start_x, start_y = start_lng, start_lat
        end_x, end_y = end_lng, end_lat

    # Map points to the nearest edges for more accurate routing
    start_u, start_v, start_k, p_start_x, p_start_y, dist = map_matcher.snap_to_edge(start_x, start_y, max_dist_m=200.0)
    end_u, end_v, end_k, p_end_x, p_end_y, dist = map_matcher.snap_to_edge(end_x, end_y, max_dist_m=200.0)
    logger.info(f"Nhận được yêu cầu tìm đường từ ({start_lat}, {start_lng}) đến ({end_lat}, {end_lng})")
    logger.info(f"Start point: ({p_start_x}, {p_start_y}), End point: ({p_end_x}, {p_end_y})")
    
    if to_wgs84:
        snapped_start_lng, snapped_start_lat = to_wgs84.transform(p_start_x, p_start_y)
        snapped_end_lng, snapped_end_lat = to_wgs84.transform(p_end_x, p_end_y)
        logger.info(f"Điểm xuất phát sau khi chiếu: ({snapped_start_lat}, {snapped_start_lng}), Điểm đích sau khi chiếu: ({snapped_end_lat}, {snapped_end_lng})")

    if start_u == end_u and start_v == end_v:
        logger.info("Điểm xuất phát và điểm đích nằm trên cùng một cạnh. Không cần tìm đường.")
        return None, None, None

    # Dùng heuristic function để tính toán thời gian ước lượng từ node hiện tại đến điểm đích
    heuristic_func = lambda point, node: calc_time_from_point_to_node(point, node, traffic_manager.G)

    # Run A* in a separate thread to avoid blocking the event loop, since it's CPU-bound
    try:
        path, total_time_s = await asyncio.to_thread(
            custom_astar_path,
            traffic_manager,
            (start_u, start_v),
            (p_start_x, p_start_y),
            (end_u, end_v),
            (p_end_x, p_end_y),
            heuristic_func
        )
        
        total_distance_m = 0
        edge_times = []
        accumulated_s = 0.0  #Thời gian tích luỹ
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = traffic_manager.G[u][v]
            
            # Chọn bucket thời gian giống A* (900s = 15 phút)
            time_idx = min(int(accumulated_s // 900), 3)
            tw = traffic_manager.time_weights[time_idx]
            # ponytail: Tối ưu loop
            if len(edges) == 1:
                best_k = 0
                edge_time_s = tw.get((u, v, 0), 10.0)
            else:
                best_k = min(edges, key=lambda k: tw.get((u, v, k), 10.0))
                edge_time_s = tw.get((u, v, best_k), 10.0)
            accumulated_s += edge_time_s
            total_distance_m += edges[best_k].get('length', 0)
            edge_times.append(round(edge_time_s / 60, 4))
        
        distance_km = round(total_distance_m / 1000, 2)
        estimated_time_min = round(total_time_s / 60, 2)
        logger.info(f"Tìm thấy đường đi: {distance_km} km, thời gian dự kiến: {estimated_time_min} phút")
        return path, distance_km, estimated_time_min, edge_times, start_lng, start_lat, end_lng, end_lat
    except nx.NetworkXNoPath:
        logger.info("Không tìm thấy đường đi giữa hai điểm.")
        return None, None, None, None, None, None, None, None
    except Exception as e:
        logger.exception(f"Lỗi: {e}")
        return None, None, None, None, None, None, None, None
    