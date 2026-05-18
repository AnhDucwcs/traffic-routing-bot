import asyncio
import httpx
import pydantic
from aiogram import Bot, types, Dispatcher
from aiogram.filters import Command
from app.core.logger import logger
from app.core.config import settings
from app.models.user_session import UserSession
from app.services.routing.service import RoutingService as rs


class BotAdapter:
    def __init__(self, app):
        token = settings.TELEGRAM_BOT_TOKEN
        self.bot = Bot(token=token)
        self.app = app
        self.dp = Dispatcher()
        self.dp.message.register(self.handle_message, Command(commands=["start", "route"]))
        self.dp.message.register(self.handle_location, lambda message: message.location is not None)
    
    async def handle_message(self, message: types.Message):
        logger.info(f"Received message: {message.text} from {message.from_user.id}")
        if message.text.startswith("/start"):
            await message.answer("Chào mừng bạn đến với Traffic Routing Bot! Nhập lệnh /route để bắt đầu.")
        elif message.text.startswith("/route"):
            session = self.app.state.user_sessions.get(message.chat.id)
            if not session:
                self.app.state.user_sessions[message.chat.id] = UserSession(chat_id=message.chat.id, state="awaiting_start")
            else:
                session.state = "awaiting_start"
            await message.answer("Vui lòng gửi vị trí hiện tại của bạn.") 
    
    async def handle_location(self, message: types.Message):
        lat = message.location.latitude
        lng = message.location.longitude
        user_id = message.from_user.id
        lock = None
        try:
            lock = self.app.state.user_session_locks[user_id]
        except Exception:
            lock = None
        async def _process():
            try:
                session = self.app.state.user_sessions.get(user_id)
                if not session:
                    await message.answer("Vui lòng nhập lệnh /route để bắt đầu trước khi gửi vị trí.")
                if session and session.state == "awaiting_start":
                    session.start_lat = lat
                    session.start_lng = lng
                    await message.answer("Vị trí bắt đầu đã được nhận. Vui lòng gửi vị trí đích đến.")
                    session.state = "awaiting_end"
                elif session and session.state == "awaiting_end":
                    end_lat = lat
                    end_lng = lng
                    await message.answer("Vị trí đích đã được nhận. Đang tính toán lộ trình...")
                    path = await rs.find_path(self.app.state.graph, session.start_lat, session.start_lng, end_lat, end_lng)
                    try:
                        del self.app.state.user_sessions[message.chat.id]
                        del self.app.state.user_session_locks[message.chat.id]
                    except KeyError:
                        pass
                    await self.send_route_result(message, message.chat.id, self.app.state.graph, path)
            except Exception as e:
                await message.answer("Đã có lỗi xảy ra khi xử lý vị trí của bạn.")
                logger.exception(f"Error processing location for chat_id {message.chat.id}: ")
        if lock is not None:
            async with lock:
                return await _process()
        else:
            return await _process()
            
    async def send_route_result(self, message: types.Message, chat_id: int, graph, path):
        if not path:
            await message.answer("Không tìm thấy lộ trình nào.")
            return
        url = rs.generate_google_maps_url(graph, path)
        await message.answer(f"Route found with {len(path)} steps! \n\nView the route on Google Maps: {url}")
    
    async def start_telegram_bot(self, user_sessions, graph):
        logger.info("Starting Telegram bot...")
        await self.bot.delete_webhook(drop_pending_updates=True)  # Xóa webhook cũ nếu có để tránh xung đột
        await self.dp.start_polling(self.bot)
            
