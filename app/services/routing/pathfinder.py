import networkx as nx
import osmnx as ox
import asyncio
import math
from pyproj import Transformer

def calc_euclidean(u, v, graph):
    x1, y1 = graph.nodes[u]['x'], graph.nodes[u]['y']
    x2, y2 = graph.nodes[v]['x'], graph.nodes[v]['y']
    h = math.hypot(x2 - x1, y2 - y1)
    return h

async def find_shortest_path(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    # Initialize transformer to convert from WGS84 (lat/lng) to the graph's CRS (UTM)
    # Note: always_xy=True ensures that we input (lng, lat) and get (x, y) in the projected CRS
    transformer = Transformer.from_crs("EPSG:4326", graph.graph['crs'], always_xy=True)
    
    start_x, start_y = transformer.transform(start_lng, start_lat)
    end_x, end_y = transformer.transform(end_lng, end_lat)

    # Find nearest nodes in the graph to the start and end coordinates
    start_node = ox.distance.nearest_nodes(graph, X=start_x, Y=start_y)
    end_node = ox.distance.nearest_nodes(graph, X=end_x, Y=end_y)
    print(f"Start node: {start_node}, End node: {end_node}")

    if start_node == end_node:
        print("Start and end nodes are the same. No path needed.")
        return []

    # Since A* in networkx expects a heuristic function with signature heuristic(u, v), we use a lambda to pass the graph
    heuristic_func = lambda u, v: calc_euclidean(u, v, graph)

    # Run A* in a separate thread to avoid blocking the event loop, since it's CPU-bound
    try:
        path = await asyncio.to_thread(
            nx.astar_path, graph, start_node, end_node, heuristic=heuristic_func, weight="length"
        )
        return path
    except nx.NetworkXNoPath:
        print("No path found between the specified nodes.")
        return []
    except Exception as e:
        print(f"Lỗi: {e}")
        return []