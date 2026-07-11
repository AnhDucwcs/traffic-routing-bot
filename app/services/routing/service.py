from app.services.routing import pathfinder
from pyproj import Transformer

class RoutingService:
    # Dịch vụ này sẽ cung cấp các phương thức để tìm đường, chuyển đổi định dạng, v.v.
    async def find_path(self, traffic_manager, map_matcher, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        return await pathfinder.find_shortest_path(traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng)

    def to_geojson(self, traffic_manager, path, geom_dict, start_lng, start_lat, end_lng, end_lat, edge_times=None):
        if not path:
            return None
            
        transformer_back = Transformer.from_crs(traffic_manager.G.graph['crs'], "EPSG:4326", always_xy=True)
        coordinates = []
        coordinates.append((start_lng, start_lat))
        # Lắp ráp từng đoạn cong (LineString) của các cạnh
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = traffic_manager.G[u][v]
            best_key = min(edges.keys(), key=lambda k: edges[k].get('current_weight', float('inf')))
            line = geom_dict.get((u, v, best_key))
            
            if line:
                for x, y in line.coords:
                    lng, lat = transformer_back.transform(x, y)
                    if not coordinates or coordinates[-1] != (lng, lat):
                        coordinates.append((lng, lat))
            else:
                # Fallback vẽ đường thẳng nếu không tìm thấy geometry
                u_x, u_y = traffic_manager.G.nodes[u]['x'], traffic_manager.G.nodes[u]['y']
                v_x, v_y = traffic_manager.G.nodes[v]['x'], traffic_manager.G.nodes[v]['y']
                lng_u, lat_u = transformer_back.transform(u_x, u_y)
                lng_v, lat_v = transformer_back.transform(v_x, v_y)
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
