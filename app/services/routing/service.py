from app.services.routing import pathfinder
from pyproj import Transformer

class RoutingService:
    # Dịch vụ này sẽ cung cấp các phương thức để tìm đường, chuyển đổi định dạng, v.v.
    async def find_path(self, traffic_manager, map_matcher, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        return await pathfinder.find_shortest_path(traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng)

    def to_geojson(self, traffic_manager, path, geom_dict, start_lng, start_lat, end_lng, end_lat, edge_times=None):
        if not path:
            return None
            
        _, to_wgs84 = traffic_manager.to_graph, traffic_manager.to_wgs84
        coordinates = []
        coordinates.append((start_lng, start_lat))
        accumulated_s = 0.0
        
        # Lắp ráp từng đoạn cong (LineString) của các cạnh
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = traffic_manager.G[u][v]
            
            time_idx = min(int(accumulated_s // 900), 3)
            tw = traffic_manager.time_weights[time_idx]
            best_key = min(edges.keys(), key=lambda k: tw.get((u, v, k), 10.0))
            
            if edge_times and i < len(edge_times):
                accumulated_s += edge_times[i] * 60
                
            line = geom_dict.get((u, v, best_key))
            
            if line:
                coords = list(line.coords)
                u_x, u_y = traffic_manager.G.nodes[u]['x'], traffic_manager.G.nodes[u]['y']
                
                # So sánh khoảng cách để biết LineString có bị ngược chiều xe chạy không
                dist_to_start = (coords[0][0] - u_x)**2 + (coords[0][1] - u_y)**2
                dist_to_end = (coords[-1][0] - u_x)**2 + (coords[-1][1] - u_y)**2
                
                # Nếu ngược, lật mảng lại!
                if dist_to_end < dist_to_start:
                    coords = coords[::-1]
                for x, y in coords:
                    lng, lat = to_wgs84.transform(x, y)
                    if not coordinates or coordinates[-1] != (lng, lat):
                        coordinates.append((lng, lat))
            else:
                # Fallback vẽ đường thẳng nếu không tìm thấy geometry
                u_x, u_y = traffic_manager.G.nodes[u]['x'], traffic_manager.G.nodes[u]['y']
                v_x, v_y = traffic_manager.G.nodes[v]['x'], traffic_manager.G.nodes[v]['y']
                lng_u, lat_u = to_wgs84.transform(u_x, u_y)
                lng_v, lat_v = to_wgs84.transform(v_x, v_y)
                if not coordinates or coordinates[-1] != (lng_u, lat_u):
                    coordinates.append((lng_u, lat_u))
                if coordinates[-1] != (lng_v, lat_v):
                    coordinates.append((lng_v, lat_v))
                    
        if coordinates[-1] != (end_lng, end_lat):
            coordinates.append((end_lng, end_lat))

        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {"edge_times": edge_times or []},
        }

routing_service = RoutingService()
