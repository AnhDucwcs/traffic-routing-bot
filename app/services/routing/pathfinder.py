import networkx as nx
import osmnx as ox
import asyncio
import math
import heapq
import itertools
from pyproj import Transformer
from app.core.logger import logger

WAYPOINT_ANGLE_THRESHOLD: float = 25.0


def _get_transformers(graph):
    graph_crs = graph.graph.get('crs')
    if not graph_crs or str(graph_crs).upper() == 'EPSG:4326':
        return None, None
    to_graph = Transformer.from_crs('EPSG:4326', graph_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(graph_crs, 'EPSG:4326', always_xy=True)
    return to_graph, to_wgs84

def calc_time_from_euclidean(u, v, graph):
    x1, y1 = graph.nodes[u]['x'], graph.nodes[u]['y']
    x2, y2 = graph.nodes[v]['x'], graph.nodes[v]['y']
    h = math.hypot(x2 - x1, y2 - y1)
    t = h / 12.5 # Tốc độ là 45km/h
    return t

def custom_astar_path(traffic_manager, source, target, heuristic_func):
    """Thuật toán A* tùy chỉnh, hỗ trợ phạt góc rẽ và dùng Min-Heap (O(log N))"""
    c = itertools.count()
    open_set = []
    heapq.heappush(open_set, (0, next(c), source, None, 0))
    g_score = {(source, None): 0}
    
    came_from = {}
    
    while open_set:
        f, _, current, prev_node, current_g = heapq.heappop(open_set)
        
        if current == target:
            path = [current]
            curr_state = (current, prev_node)
            while curr_state in came_from:
                curr_state = came_from[curr_state]
                if curr_state[0] is not None:
                    path.append(curr_state[0])
            path.reverse()
            return path, current_g
        
        # Nếu nhánh hiện tại có chi phí đắt hơn nhánh đã khám phá, bỏ qua
        if current_g > g_score.get((current, prev_node), float('inf')):
            continue
            
        for neighbor in traffic_manager.G.successors(current):
            # Lấy trọng số thực tế (xử lý MultiDiGraph)
            edges = traffic_manager.G[current][neighbor]
            edge_data = min(edges.values(), key=lambda x: x.get('current_weight', float('inf')))
            travel_time = edge_data.get('current_weight', 10.0)
            
            # GỌI HÀM PHẠT GÓC RẼ
            turn_penalty = traffic_manager.turn_penalties.get((prev_node, current, neighbor), 0.0)
            
            # Ép xung A* với Bounded Suboptimal (Epsilon = 1.15)
            h_val = heuristic_func(neighbor, target) * 1.15
            
            tentative_g = current_g + travel_time + turn_penalty
            
            if tentative_g < g_score.get((neighbor, current), float('inf')):
                g_score[(neighbor, current)] = tentative_g
                f_score = tentative_g + h_val
                came_from[(neighbor, current)] = (current, prev_node)
                heapq.heappush(open_set, (f_score, next(c), neighbor, current, tentative_g))
                
    raise nx.NetworkXNoPath(f"Không tìm thấy đường từ {source} đến {target}")

async def find_shortest_path(traffic_manager, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    to_graph, _ = _get_transformers(traffic_manager.G)

    if to_graph:
        start_x, start_y = to_graph.transform(start_lng, start_lat)
        end_x, end_y = to_graph.transform(end_lng, end_lat)
    else:
        start_x, start_y = start_lng, start_lat
        end_x, end_y = end_lng, end_lat

    # Find nearest nodes in the graph to the start and end coordinates
    start_node = ox.distance.nearest_nodes(traffic_manager.G, X=start_x, Y=start_y)
    end_node = ox.distance.nearest_nodes(traffic_manager.G, X=end_x, Y=end_y)
    logger.info(f"Nhận được yêu cầu tìm đường từ ({start_lat}, {start_lng}) đến ({end_lat}, {end_lng})")
    logger.info(f"Start node: {start_node}, End node: {end_node}")

    if start_node == end_node:
        logger.info("Start and end nodes are the same. No path needed.")
        return None, None, None

    # Since A* in networkx expects a heuristic function with signature heuristic(u, v), we use a lambda to pass the graph
    heuristic_func = lambda u, v: calc_time_from_euclidean(u, v, traffic_manager.G)

    # Run A* in a separate thread to avoid blocking the event loop, since it's CPU-bound
    try:
        path, total_time_s = await asyncio.to_thread(
            custom_astar_path,
            traffic_manager,
            start_node,
            end_node,
            heuristic_func
        )
        
        total_distance_m = 0
        edge_times = []
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = traffic_manager.G[u][v]
            
            best_edge = min(edges.values(), key=lambda x: x.get('current_weight', float('inf')))
            
            edge_time_s = best_edge.get('current_weight', 0)
            total_distance_m += best_edge.get('length', 0)
            edge_times.append(round(edge_time_s / 60, 4)) # Store time in minutes per edge
        
        distance_km = round(total_distance_m / 1000, 2)
        estimated_time_min = round(total_time_s / 60, 2)
        logger.info(f"Found path with distance: {distance_km} km, estimated time: {estimated_time_min} minutes")
        return path, distance_km, estimated_time_min, edge_times
    except nx.NetworkXNoPath:
        logger.info("No path found between the specified nodes.")
        return None, None, None, None
    except Exception as e:
        logger.exception(f"Lỗi: {e}")
        return None, None, None, None
    