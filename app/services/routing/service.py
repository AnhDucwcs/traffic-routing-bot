from app.services.routing import pathfinder


class RoutingService:
    """Thin wrapper around pathfinder functionality to expose a stable service API."""

    async def find_path(self, graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        return await pathfinder.find_shortest_path(graph, start_lat, start_lng, end_lat, end_lng)

    def generate_google_maps_url(self, graph, path):
        return pathfinder.generate_google_maps_url(graph, path)

    def to_geojson(self, graph, path):
        if not path:
            return None
        transformer_back = pathfinder.Transformer.from_crs(graph.graph['crs'], "EPSG:4326", always_xy=True)
        coordinates = []
        for node in path:
            x, y = graph.nodes[node]['x'], graph.nodes[node]['y']
            lng, lat = transformer_back.transform(x, y)
            coordinates.append((lng, lat))
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {},
        }


routing_service = RoutingService()
