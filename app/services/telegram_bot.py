from time import time

import httpx
from fastapi import Request
from app.core.config import settings
from app.models import request_models
from app.models.user_session import UserSession
from app.services.routing.pathfinder import find_shortest_path, generate_google_maps_url
from pyproj import Transformer

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
    
    async def process_update(self, update: request_models.TelegramUpdate, user_session, graph):
        if update.message:
            chat_id = update.message.chat.id
            text = update.message.text
            location = update.message.location
        elif update.edited_message:
            chat_id = update.edited_message.chat.id
            text = update.edited_message.text
            location = update.edited_message.location
        else:
            print("Update does not support")
            return {"status": "unsupported update type", "update_id": update.update_id}
        
        if text == "/route":
            user_session[chat_id] = UserSession(chat_id=chat_id, state="awaiting_start", last_updated=time.time())
            await bot.send_message(chat_id, "Please send your starting location.")
            return {"status": "awaiting_start"}
        
        if location:
            if chat_id not in user_session:
                await bot.send_message(chat_id, "Please enter '/route' to start a new routing session.")
                return {"status": "user_session not found"}
            elif user_session[chat_id].state == "awaiting_start":
                user_session[chat_id].start_lat = location.latitude
                user_session[chat_id].start_lng = location.longitude
                user_session[chat_id].state = "awaiting_end"
                user_session[chat_id].last_updated = time.time()
                await bot.send_message(chat_id, "Starting location received. Please send your destination location.")
                return {"status": "awaiting_end"}
            elif user_session[chat_id].state == "awaiting_end":
                end_lat = location.latitude
                end_lng = location.longitude
                user_session[chat_id].state = "completed"
                await bot.send_message(chat_id, "Destination location received. Calculating route...")
                
                path = await find_shortest_path(graph, user_session[chat_id].start_lat, user_session[chat_id].start_lng, end_lat, end_lng)
                
                del user_session[chat_id]
                
                if not path:
                    await bot.send_message(chat_id, "Sorry, I couldn't find a route between those locations.")
                    return {"status": "no route found"}
                else:
                    transformer_back = Transformer.from_crs(graph.graph['crs'], "EPSG:4326", always_xy=True)
                    coordinates = []
                    for node in path:
                        x, y = graph.nodes[node]['x'], graph.nodes[node]['y']
                        lng, lat = transformer_back.transform(x, y)
                        coordinates.append((lng, lat))
                    geojson_route = {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coordinates
                        },
                        "properties": {}
                    }
                    await bot.send_message(chat_id, f"Route found with {len(path)} steps!")
                    google_maps_url = generate_google_maps_url(graph, path)
                    if google_maps_url:
                        await bot.send_message(chat_id, f"View the route on Google Maps: {google_maps_url}")
                    return {"status": "route found", "steps": len(path), "geojson": geojson_route}

bot = TelegramBot()
