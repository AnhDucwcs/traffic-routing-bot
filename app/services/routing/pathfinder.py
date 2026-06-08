import networkx as nx
import osmnx as ox
import asyncio
import math
from pyproj import Transformer
from app.core.logger import logger

def calc_time_from_euclidean(u, v, graph):
    x1, y1 = graph.nodes[u]['x'], graph.nodes[u]['y']
    x2, y2 = graph.nodes[v]['x'], graph.nodes[v]['y']
    h = math.hypot(x2 - x1, y2 - y1)
    t = h / 22.2  # Tốc độ là 80km/h
    return t

async def find_shortest_path(traffic_manager, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    # Initialize transformer to convert from WGS84 (lat/lng) to the graph's CRS (UTM)
    # Note: always_xy=True ensures that we input (lng, lat) and get (x, y) in the projected CRS
    transformer = Transformer.from_crs("EPSG:4326", traffic_manager.G.graph['crs'], always_xy=True)
    
    start_x, start_y = transformer.transform(start_lng, start_lat)
    end_x, end_y = transformer.transform(end_lng, end_lat)

    # Find nearest nodes in the graph to the start and end coordinates
    start_node = ox.distance.nearest_nodes(traffic_manager.G, X=start_x, Y=start_y)
    end_node = ox.distance.nearest_nodes(traffic_manager.G, X=end_x, Y=end_y)
    logger.info(f"Start node: {start_node}, End node: {end_node}")

    if start_node == end_node:
        logger.info("Start and end nodes are the same. No path needed.")
        return []

    # Since A* in networkx expects a heuristic function with signature heuristic(u, v), we use a lambda to pass the graph
    heuristic_func = lambda u, v: calc_time_from_euclidean(u, v, traffic_manager.G)

    # Run A* in a separate thread to avoid blocking the event loop, since it's CPU-bound
    try:
        path = await asyncio.to_thread(
            nx.astar_path, traffic_manager.G, start_node, end_node, heuristic=heuristic_func, weight="current_weight"
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
        return []
    except Exception as e:
        logger.exception(f"Lỗi: {e}")
        return []
    
def generate_google_maps_url(traffic_manager, path):
    if not path:
        return None
    
    transformer_back = Transformer.from_crs(traffic_manager.G.graph['crs'], "EPSG:4326", always_xy=True)
    
    start_lng, start_lat = transformer_back.transform(traffic_manager.G.nodes[path[0]]['x'], traffic_manager.G.nodes[path[0]]['y'])
    end_lng, end_lat = transformer_back.transform(traffic_manager.G.nodes[path[-1]]['x'], traffic_manager.G.nodes[path[-1]]['y'])
    
    # Choosing up to 8 waypoints from the internal nodes of the path
    internal_nodes = path[1:-1]
    waypoints_coords = []
    if internal_nodes:
        step = max(1, len(internal_nodes) // 8)
        selected_nodes = internal_nodes[::step][:8]
        for node in selected_nodes:
            x, y = traffic_manager.G.nodes[node]['x'], traffic_manager.G.nodes[node]['y']
            lng, lat = transformer_back.transform(x, y)
            waypoints_coords.append(f"{lat},{lng}")
    
    waypoints_str = "|".join(waypoints_coords)
    logger.info(f"Generated Google Maps URL with start: ({start_lat}, {start_lng}), end: ({end_lat}, {end_lng})")
    
    url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lng}&destination={end_lat},{end_lng}"
    if waypoints_str:
        url += f"&waypoints={waypoints_str}"
    url += "&travelmode=driving"
    
    return url