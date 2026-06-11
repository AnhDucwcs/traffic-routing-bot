import networkx as nx
import osmnx as ox
import asyncio
import math
import urllib.parse
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
    t = h / 22.2  # Tốc độ là 80km/h
    return t

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
        path = await asyncio.to_thread(
            nx.astar_path, 
            traffic_manager.G, 
            start_node, 
            end_node, 
            heuristic=heuristic_func, 
            weight="current_weight"
        )
        
        total_distance_m = 0
        total_time_s = 0
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = traffic_manager.G[u][v]
            
            best_edge = min(edges.values(), key=lambda x: x.get('current_weight', float('inf')))
            
            total_distance_m += best_edge.get('length', 0)
            total_time_s += best_edge.get('current_weight', 0)
        
        distance_km = round(total_distance_m / 1000, 2)
        estimated_time_min = round(total_time_s / 60, 2)
        logger.info(f"Found path with distance: {distance_km} km, estimated time: {estimated_time_min} minutes")
        return path, distance_km, estimated_time_min
    except nx.NetworkXNoPath:
        logger.info("No path found between the specified nodes.")
        return None, None, None
    except Exception as e:
        logger.exception(f"Lỗi: {e}")
        return None, None, None
    
def calculate_angle(p1, p2, p3):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    
    angle1 = math.atan2(y2 - y1, x2 - x1)
    angle2 = math.atan2(y3 - y2, x3 - x2)
    
    degree = math.degrees(angle2 - angle1)
    degree = abs(degree) % 360
    if degree > 180:
        degree = 360 - degree
    
    return abs(degree)    

def optimize_waypoints_for_google_maps(path_coords, max_waypoints=8):
    if len(path_coords) <= max_waypoints + 2:
        return []

    turn_points = []
    for i in range(1, len(path_coords) - 1):
        angle = calculate_angle(path_coords[i - 1], path_coords[i], path_coords[i + 1])
        if angle > WAYPOINT_ANGLE_THRESHOLD:  # Threshold for a "turn"
            turn_points.append((i, path_coords[i - 1]))
    
    filtered_points = []
    last_added_idx = -99
    
    for node_idx, coord in turn_points:
        if node_idx - last_added_idx > 2:
            filtered_points.append(coord)
            last_added_idx = node_idx
    
    if len(filtered_points) > max_waypoints:
        step = len(filtered_points) / float(max_waypoints)
        final_waypoints = [filtered_points[int(math.floor(i * step))] for i in range(max_waypoints)]
    else:
        final_waypoints = filtered_points

    return final_waypoints[:8]
    
    
def generate_google_maps_url(traffic_manager, path):
    if not path:
        return None
    
    _, to_wgs84 = _get_transformers(traffic_manager.G)
    path_coords = []
    for node in path:
        x = traffic_manager.G.nodes[node]['x']
        y = traffic_manager.G.nodes[node]['y']
        if to_wgs84:
            lng, lat = to_wgs84.transform(x, y)
        else:
            lng, lat = x, y
        path_coords.append((lat, lng)) # Google Maps dùng định dạng Lat, Lng
    
    start_lat, start_lng = path_coords[0]
    end_lat, end_lng = path_coords[-1]
    
    # Choosing up to 8 waypoints from the internal nodes of the path
    optimized_waypoints = optimize_waypoints_for_google_maps(path_coords, max_waypoints=8)
    waypoints_coords = []
    for lat, lng in optimized_waypoints:
        if (lat, lng) != (start_lat, start_lng) and (lat, lng) != (end_lat, end_lng):
            waypoints_coords.append(f"{lat},{lng}")
    
    waypoints_str = "|".join(waypoints_coords)
    logger.info(f"Generated Google Maps URL with start: ({start_lat}, {start_lng}), end: ({end_lat}, {end_lng})")
    
    url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lng}&destination={end_lat},{end_lng}"
    if waypoints_str:
        url += f"&waypoints={urllib.parse.quote(waypoints_str)}"
    url += "&travelmode=two-wheeler"
    
    return url