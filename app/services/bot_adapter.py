import asyncio
import httpx
import pydantic
from aiogram import Bot, types, Dispatcher, F
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from app.core.logger import logger
from app.core.config import settings
from app.models.schemas import RoutingRequest
from app.models.user_session import UserSession
from app.services.core_logic import process_routing_request
from app.services.routing.service import RoutingService as rs


class BotAdapter:
    def __init__(self, app):
        token = settings.TELEGRAM_BOT_TOKEN
        proxy_url = (settings.VN_PROXY or "").strip()
        if proxy_url:
            logger.info("Khởi tạo Telegram Bot với VN_PROXY...")
            session = AiohttpSession(proxy=proxy_url)
            self.bot = Bot(token=token, session=session)
        else:
            self.bot = Bot(token=token)
        self.app = app
        self.dp = Dispatcher()
        self.dp.message.register(self.handle_message, Command(commands=["start", "route"]))
        self.dp.message.register(self.handle_location, F.location)
    
    async def handle_message(self, message: types.Message):
        logger.info(f"Received message: {message.text} from {message.from_user.id}")
        if message.text.startswith("/start"):
            await message.answer("Chào mừng bạn đến với Traffic Routing Bot! Nhập lệnh /route để bắt đầu.")
        elif message.text.startswith("/route"):
            session_id = f"telegram_{message.chat.id}"
            session = self.app.state.user_sessions.get(session_id)
            if not session:
                self.app.state.user_sessions[session_id] = UserSession(chat_id=message.chat.id, state="awaiting_start")
            else:
                session.state = "awaiting_start"
            await message.answer("Vui lòng gửi vị trí hiện tại của bạn.") 
            
    async def handle_location(self, message: types.Message):
        payload = RoutingRequest(
            user_id=str(message.from_user.id),
            platform="telegram",
            latitude=message.location.latitude,
            longitude=message.location.longitude
        )
        result_text = await process_routing_request(payload, self.app.state)
        if result_text["status"] == "success":
            await message.answer(result_text["message"])
            await message.answer(result_text["url"])
        else:
            await message.answer(result_text["message"])
    
    
    async def start_telegram_bot(self, user_sessions, graph):
        logger.info("Starting Telegram bot...")
        await self.bot.delete_webhook(drop_pending_updates=True)  # Xóa webhook cũ nếu có để tránh xung đột
        await self.dp.start_polling(self.bot)
            
