from app.services.routing import pathfinder


class RoutingService:
    # Dịch vụ này sẽ cung cấp các phương thức để tìm đường, chuyển đổi định dạng, v.v.
    async def find_path(self, traffic_manager, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        return await pathfinder.find_shortest_path(traffic_manager, start_lat, start_lng, end_lat, end_lng)


    def to_geojson(self, traffic_manager, path):
        if not path:
            return None
        transformer_back = pathfinder.Transformer.from_crs(traffic_manager.G.graph['crs'], "EPSG:4326", always_xy=True)
        coordinates = []
        for node in path:
            x, y = traffic_manager.G.nodes[node]['x'], traffic_manager.G.nodes[node]['y']
            lng, lat = transformer_back.transform(x, y)
            coordinates.append((lng, lat))
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {},
        }


routing_service = RoutingService()
