import httpx
from app.core.config import settings
from app.models.user_session import UserSession

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
        user_sessions[chat_id] = UserSession(chat_id=chat_id, state="awaiting_start")
        await self.send_message(chat_id, "Please send your starting location.")
        return {"status":"awaiting_start"}
    
    async def _handle_location(self, chat_id, loc, user_sessions, graph):
        # Use per-chat lock if available to avoid race conditions
        lock = None
        try:
            lock = self.user_session_locks[chat_id]
        except Exception:
            lock = None

        async def _process():
            sess = user_sessions.get(chat_id)
            if not sess:
                await self.send_message(chat_id, "Please enter '/route' to start...")
                return {"status":"no_session"}
            if sess.state == "awaiting_start":
                sess.start_lat = loc.latitude
                sess.start_lng = loc.longitude
                sess.state = "awaiting_end"
                await self.send_message(chat_id, "Starting location received. Please send your destination location.")
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

        if lock is not None:
            async with lock:
                return await _process()
        else:
            return await _process()

    async def _send_route_result(self, chat_id, path, graph):
        if not path:
            await self.send_message(chat_id, "Sorry, I couldn't find a route between those locations.")
            return {"status": "no route found"}

        geojson_route = None
        try:
            geojson_route = self.routing_service.to_geojson(graph, path)
        except Exception:
            geojson_route = None

        await self.send_message(chat_id, f"Route found with {len(path)} steps!")
        google_maps_url = None
        try:
            google_maps_url = self.routing_service.generate_google_maps_url(graph, path)
        except Exception:
            google_maps_url = None

        if google_maps_url:
            await self.send_message(chat_id, f"View the route on Google Maps: {google_maps_url}")

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

