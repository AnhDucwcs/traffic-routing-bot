from app.models.schemas import RoutingResponse

def create_success_response(user_id, conversation_id, geojson, route_id, distance, time, metadata=None):
    return RoutingResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        status="success",
        message="Lộ trình tối ưu của bạn đã sẵn sàng.",
        distance_km=distance,
        estimated_time_min=time,
        geojson=geojson,
        route_id=route_id,
        metadata=metadata or {}
    )

def create_error_response(user_id, conversation_id, message: str):
    return RoutingResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        status="error",
        message=message,
        metadata={}
    )