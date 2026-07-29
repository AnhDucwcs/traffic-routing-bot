from fastapi import APIRouter
from fastapi import Request
from fastapi import BackgroundTasks, Header, HTTPException
import httpx
import time
import uuid
from app.models.schemas import RoutingRequest, ReportRequest
from app.services.response_helper import create_success_response, create_error_response
from app.core.config import settings
from app.core.logger import logger


router = APIRouter()




@router.get("/")
async def root():
    return {"message": "Welcome to the Traffic Routing Bot API!"}

@router.get("/health-check")
@router.head("/health-check")
async def health_check():
    return {"status": "healthy"}

async def process_routing_background(payload: RoutingRequest, app_state):
    logger.info(f"Bắt đầu xử lý ngầm: Conversation {payload.conversation_id}")
    start_time = time.perf_counter()
    user_id = payload.user_id
    conversation_id = payload.conversation_id
    
    # 1. Lấy tọa độ từ payload
    start_lat = payload.origin.latitude
    start_lng = payload.origin.longitude
    end_lat = payload.destination.latitude
    end_lng = payload.destination.longitude
    logger.info(f"Yêu cầu lộ trình từ ({start_lat}, {start_lng}) đến ({end_lat}, {end_lng})")
    traffic_manager = app_state.traffic_manager
    map_matcher = app_state.map_matcher
    try:
        path, distance_km, estimated_time_min, edge_times, source_lng, source_lat, dest_lng, dest_lat = await app_state.routing_service.find_path(traffic_manager, map_matcher, start_lat, start_lng, end_lat, end_lng)

        # Đo thời gian
        execution_time = time.perf_counter() - start_time
        logger.info(f"Tính toán lộ trình mất {execution_time:.4f} giây")

        if path is None:
            data = create_error_response(user_id, conversation_id, "Không tìm thấy lộ trình phù hợp.")
        else:
            geojson = app_state.routing_service.to_geojson(
                traffic_manager, path, app_state.geom_dict, 
                source_lng, source_lat, dest_lng, dest_lat,
                edge_times
            )
            route_id = str(uuid.uuid4())
            app_state.route_results[route_id] = {
                "geojson": geojson,
            }
            data = create_success_response(user_id, conversation_id, geojson, route_id, distance_km, estimated_time_min)
    except ValueError as e:
        data = create_error_response(user_id, conversation_id, str(e))
    except Exception as e:
        logger.exception(f"Lỗi khi xử lý lộ trình: {e}")
        data = create_error_response(user_id, conversation_id, f"Lỗi khi xử lý lộ trình: {e}")

    response_payload = data.model_dump()
 
    if payload.platform == "telegram":
        callback_url = settings.TELEGRAM_BOT_CALLBACK_URL
    elif payload.platform == "java_app":
        callback_url = settings.JAVA_APP_CALLBACK_URL
    else:
        logger.error(f"Platform không hợp lệ: {payload.platform}")
        return

    if not callback_url:
        logger.error(f"Bỏ qua callback do thiếu URL cấu hình cho platform {payload.platform}, conversation: {payload.conversation_id}")
        return

    async with httpx.AsyncClient() as client:
        try:
            headers = {
                "x-internal-api-key": settings.INTERNAL_API_KEY
            }
            await client.post(
                callback_url,
                json=response_payload,
                headers=headers,
                timeout=10.0,
            )
            logger.info(f"Đã trả kết quả về Callback: {callback_url}")
        except Exception as e:
            logger.error(f"Lỗi khi gọi Callback: {e}")

@router.post("/api/v1/routing/")
async def routing_endpoint(
    payload: RoutingRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    x_internal_api_key: str = Header(..., alias="x-internal-api-key")
):
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Từ chối truy cập: Sai API Key")
        
    background_tasks.add_task(process_routing_background, payload, request.app.state)
    
    return {"status": "accepted", "message": "Đã tiếp nhận yêu cầu, đang xử lý..."}

@router.get("/api/v1/routing/result/{route_id}")
async def get_routing_result(route_id: str, request: Request):
    route_result = request.app.state.route_results.get(route_id)
    if not route_result:
        logger.exception(f"Không tìm thấy kết quả cho route_id: {route_id}")
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả lộ trình")
    logger.info(f"Trả về kết quả lộ trình cho route_id: {route_id}")
    return route_result

@router.post("/api/v1/report/")
async def crowdsource_report(
    request_data: ReportRequest, 
    request: Request,
    x_internal_api_key: str = Header(..., alias="x-internal-api-key")
):
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Từ chối truy cập: Sai API Key")
        
    crowdsource_manager = request.app.state.crowdsource_manager
    return await crowdsource_manager.report_jam(request_data)