from app.models.schemas import RoutingResponse

def _error_response(message):
    return RoutingResponse(status="error", message=message)
def _success_response(message, url = None, distance_km = None, estimated_time_min = None, geojson = None, map_image_url = None):
    return RoutingResponse(status="success", message=message, navigation_url=url, distance_km=distance_km, estimated_time_min=estimated_time_min, geojson=geojson, map_image_url=map_image_url)