from fastapi import APIRouter
from fastapi import Request
from fastapi import BackgroundTasks, Header, HTTPException
import httpx
import time
from app.models.schemas import JavaRoutingRequest
from app.services.routing.service import routing_service as rs
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

async def process_java_routing_background(payload: JavaRoutingRequest, app_state):
    logger.info(f"Bắt đầu xử lý ngầm cho Java: Conversation {payload.conversationId}")
    start_time = time.perf_counter()
    
    # 1. Lấy tọa độ từ payload
    start_lat = payload.origin.lat
    start_lng = payload.origin.lng
    end_lat = payload.destination.lat
    end_lng = payload.destination.lng

    graph = app_state.graph
    path, distance_km, estimated_time_min = await rs.find_path(graph, start_lat, start_lng, end_lat, end_lng)
    
    # Đo thời gian
    execution_time = time.perf_counter() - start_time
    logger.info(f"Tính toán lộ trình cho Java mất {execution_time:.4f} giây")

    if path is None:
        data = {
            "conversationId": payload.conversationId,
            "senderId": "BOT_ID",
            "role": "BOT",
            "type": "ROUTE_SUGGESTION",
            "text": "Xin lỗi, không tìm thấy lộ trình nào phù hợp.",
            "metadata": {
                "route": None
            },
            "status": "error"
        }
    else:
        url = rs.generate_google_maps_url(graph, path)
        data = {
            "conversationId": payload.conversationId,
            "senderId": "BOT_ID",
            "role": "BOT",
            "type": "ROUTE_SUGGESTION",
            "text": "Lộ trình tối ưu của bạn đã sẵn sàng.",
            "metadata": {
                "route": {
                    "distance_km": distance_km,
                    "estimated_time_mins": estimated_time_min,
                    "navigation_url": url
                }
            },
            "status": "success"
        }
        
    # 4. Bắn Webhook về lại cho Java
    async with httpx.AsyncClient() as client:
        try:
            # Nhớ thay bằng SECRET_KEY thực tế của dự án bạn
            headers = {"x-internal-api-key": settings.INTERNAL_API_KEY}
            await client.post(payload.callbackUrl, json=data, headers=headers, timeout=10.0)
            logger.info(f"Đã trả kết quả về Java Callback: {payload.callbackUrl}")
        except Exception as e:
            logger.error(f"Lỗi khi gọi Java Callback: {e}")

@router.post("/api/v1/routing/java")
async def java_routing_endpoint(
    payload: JavaRoutingRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    x_internal_api_key: str = Header(...)
):
    # Bảo mật: Kiểm tra API Key
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Từ chối truy cập: Sai API Key")
        
    # Đẩy tác vụ vào luồng chạy ngầm
    background_tasks.add_task(process_java_routing_background, payload, request.app.state)
    
    # Trả về HTTP 202 Accepted ngay lập tức để giải phóng App Java
    return {"status": "accepted", "message": "Đã tiếp nhận yêu cầu, đang xử lý..."}

@router.get("/api/v1/routing/result/{route_id}")
async def get_routing_result(route_id: str, request: Request):
    route_result = request.app.state.route_results.get(route_id)
    if not route_result:
        logger.exception(f"Không tìm thấy kết quả cho route_id: {route_id}")
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả lộ trình")
    logger.info(f"API đang trả về GeoJSON: {route_result}")
    return route_result