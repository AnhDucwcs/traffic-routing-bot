from app.models.schemas import RoutingResponse

def create_success_response(geojson, url, route_id, distance, time, metadata=None):
    return RoutingResponse(
        status="success",
        message="Lộ trình tối ưu của bạn đã sẵn sàng.",
        distance_km=distance,
        estimated_time_min=time,
        geojson=geojson,
        navigation_url=url,
        route_id=route_id,
        metadata=metadata or {}
    )

def create_error_response(message: str):
    return RoutingResponse(
        status="error",
        message=message,
        metadata={}
    )