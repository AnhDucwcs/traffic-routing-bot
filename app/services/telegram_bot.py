import asyncio
import httpx
import random
from app.core.config import settings
from app.models.user_session import UserSession
from app.core.logger import logger

class TelegramBot:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        #Giới hạn Connection Pool để bảo vệ Proxy không bị sập
        limits = httpx.Limits(
            max_connections=50,          # Tối đa 50 ống nước TCP mở cùng lúc ra ngoài
            max_keepalive_connections=0
        )
        proxy_url = (settings.US_PROXY or "").strip()
        timeout_config = httpx.Timeout(
            connect=10.0, 
            read=10.0, 
            write=10.0, 
            pool=10.0
        )
        # Tạo một phiên HTTPX AsyncClient tránh việc phải tạo mới mỗi lần gửi tin nhắn, đồng thời cấu hình proxy và giới hạn kết nối
        self.session = httpx.AsyncClient(timeout=timeout_config, trust_env=False, proxy=None, limits=limits) 
        
    async def send_message(self, chat_id: int, text: str):
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        # Retry 3 lần nếu gặp lỗi mạng khi gửi tin nhắn, mỗi lần cách nhau 1 giây
        for attempt in range(3):
            try:
                response = await self.session.post(url, json=payload)
                response.raise_for_status()
                return True
            except httpx.HTTPStatusError as e:
                logger.exception(f"[TelegramBot] Lỗi từ máy chủ Telegram (Status {e.response.status_code})")
            except httpx.RequestError as e:
                if attempt < 2:  # Chỉ log cảnh báo cho 2 lần đầu, lần thứ 3 sẽ log lỗi
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"[TelegramBot] Lỗi khi gửi tin nhắn (Lần {attempt + 1}/3). Đợi {sleep_time:.1f}s trước khi thử lại...")
                    await asyncio.sleep(sleep_time)
                else: 
                    logger.exception(f"Thất bại khi gửi tin nhắn đến chat_id {chat_id} sau 3 lần thử.")
        return False

    def _parse_update(self, update):
        if update.message:
            chat_id = update.message.chat.id
            text = update.message.text
            location = update.message.location
        elif update.edited_message:
            chat_id = update.edited_message.chat.id
            text = update.edited_message.text
            location = update.edited_message.location
        else:
            return None, None, None
        return chat_id, text, location
    
    async def _handle_route_command(self, chat_id, user_sessions):
        try:
            success = await self.send_message(chat_id, "Please send your starting location.")
            if not success:
                logger.error(f"Failed to send message to chat_id {chat_id} after /route command")
            else:
                user_sessions[chat_id] = UserSession(chat_id=chat_id, state="awaiting_start")
                logger.info(f"Started new routing session for chat_id {chat_id}")
            return {"status":"awaiting_start"}
        except Exception as e:
            logger.exception(f"Error handling /route command for chat_id {chat_id}: ")
            return {"status": "error"}
    
    async def _handle_location(self, chat_id, loc, user_sessions, graph):
        # Use per-chat lock if available to avoid race conditions
        lock = None
        try:
            lock = self.user_session_locks[chat_id]
        except Exception:
            lock = None

        async def _process():
            try:
                sess = user_sessions.get(chat_id)
                if not sess:
                    await self.send_message(chat_id, "Please enter '/route' to start...")
                    return {"status":"no_session"}
                if sess.state == "awaiting_start":
                    sess.start_lat = loc.latitude
                    sess.start_lng = loc.longitude
                    success = await self.send_message(chat_id, "Starting location received. Please send your destination location.")
                    if not success:
                        logger.error(f"Failed to send message to chat_id {chat_id} after receiving start location")
                        return {"status": "error"}
                    else:
                        logger.info(f"Starting location received for chat_id {chat_id}")
                        sess.state = "awaiting_end"
                        return {"status":"awaiting_end"}
                if sess.state == "awaiting_end":
                    end_lat, end_lng = loc.latitude, loc.longitude
                    # route finding handled by routing_service
                    path = await self.routing_service.find_path(graph, sess.start_lat, sess.start_lng, end_lat, end_lng)
                    try:
                        del user_sessions[chat_id]
                        del self.user_session_locks[chat_id]
                    except KeyError:
                        pass
                    return await self._send_route_result(chat_id, path, graph)
            except Exception as e:
                logger.exception(f"Error processing location for chat_id {chat_id}: ")
                return {"status": "error"}

        if lock is not None:
            async with lock:
                return await _process()
        else:
            return await _process()

    async def _send_route_result(self, chat_id, path, graph):
        if not path:
            success = await self.send_message(chat_id, "Sorry, I couldn't find a route between those locations.")
            if not success:
                logger.error(f"Error sending no route message to chat_id {chat_id}: ")
            else:
                logger.info(f"No route found for chat_id {chat_id}")
                return {"status": "error"}

        geojson_route = None
        try:
            geojson_route = self.routing_service.to_geojson(graph, path)
        except Exception as e:
            logger.exception(f"Error generating GeoJSON for chat_id {chat_id}: ")
            geojson_route = None

        success = await self.send_message(chat_id, f"Route found with {len(path)} steps!")
        if not success:
            logger.error(f"Error sending route found message to chat_id {chat_id}: ")
        else:
            logger.info(f"Route found with {len(path)} steps for chat_id {chat_id}")

        google_maps_url = None
        try:
            google_maps_url = self.routing_service.generate_google_maps_url(graph, path)
        except Exception as e:
            logger.exception(f"Error generating Google Maps URL for chat_id {chat_id}: ")
            google_maps_url = None

        if google_maps_url:
            success = await self.send_message(chat_id, f"View the route on Google Maps: {google_maps_url}")
            if not success:
                logger.error(f"Error sending Google Maps URL to chat_id {chat_id}")
            else:
                logger.info(f"Sent Google Maps URL to chat_id {chat_id}")

        return {"status": "route found", "steps": len(path), "geojson": geojson_route}
    
    async def process_update(self, update, user_sessions, graph):
        chat_id, text, location = self._parse_update(update)
        if chat_id is None:
            return {"status": "unsupported"}

        if text == "/route":
            return await self._handle_route_command(chat_id, user_sessions)

        if location:
            return await self._handle_location(chat_id, location, user_sessions, graph)

        return {"status": "ok"}

