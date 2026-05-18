import asyncio

from app.models.user_session import UserSession
from app.services.routing.service import RoutingService as rs

async def process_routing_request(payload, app_state):
    session_id = f"{payload.platform}_{payload.user_id}"
    lock = app_state.user_session_locks[session_id] # Lấy lock tương ứng với session_id, nếu chưa có sẽ tự động tạo mới do defaultdict
    async def _process():
        session = app_state.user_sessions.get(session_id)
        if not session:
            return {
                "status": "error", 
                "message": "Vui lòng nhập lệnh /route để bắt đầu."
            }
        if session.state == "awaiting_start":
            session.start_lat = payload.latitude
            session.start_lng = payload.longitude
            session.state = "awaiting_end"
            return {
                "status": "pending", 
                "message": "Đã nhận vị trí xuất phát. Vui lòng gửi vị trí đích."
            }
        elif session.state == "awaiting_end":
            end_lat = payload.latitude
            end_lng = payload.longitude  
            graph = app_state.graph
            path = await rs.find_path(graph, session.start_lat, session.start_lng, end_lat, end_lng)
            
            try:
                del app_state.user_sessions[session_id] # Xóa session sau khi đã sử dụng để tránh rác bộ nhớ
                del app_state.user_session_locks[session_id] # Xóa lock
            except KeyError:
                pass
            
            if path is None:
                return {
                    "status": "error",
                    "message": "Không tìm thấy lộ trình nào phù hợp."
                }

            url = rs.generate_google_maps_url(graph, path)
            
            return {
                "status": "success",
                "message": "Đã tính toán lộ trình thành công.",
                "url": url
            }
    if lock is not None:
        async with lock:
            return await _process()
    else:
        return await _process()