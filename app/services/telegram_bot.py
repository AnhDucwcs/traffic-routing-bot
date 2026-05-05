import httpx
from app.core.config import settings

class TelegramBot:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        # Create a single session for the bot, which can be reused for multiple requests. Avoids the overhead of creating a new session for each request.
        self.session = httpx.AsyncClient() 
        
    async def send_message(self, chat_id: int, text: str):
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        await self.session.post(url, json=payload)

bot = TelegramBot()
