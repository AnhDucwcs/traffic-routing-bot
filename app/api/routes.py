from fastapi import APIRouter, Request
from rich import text
from app.models import request_models
from app.models.user_session import UserSession
from app.services.telegram_bot import bot
from app.services.crawler.bus_crawler import crawler
from app.services.routing.pathfinder import find_shortest_path, generate_google_maps_url
import time
from pyproj import Transformer

router = APIRouter()

@router.get("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/webhook")
async def telegram_webhook(update: request_models.TelegramUpdate, request: Request):
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
        
    session = request.app.state.user_sessions
    
    if text == "/route":
        session[chat_id] = UserSession(chat_id=chat_id, state="awaiting_start", last_updated=time.time())
        await bot.send_message(chat_id, "Please send your starting location.")
        return {"status": "awaiting_start"}
    
    if location:
        if chat_id not in session:
            await bot.send_message(chat_id, "Please enter '/route' to start a new routing session.")
            return {"status": "session not found"}
        elif session[chat_id].state == "awaiting_start":
            session[chat_id].start_lat = location.latitude
            session[chat_id].start_lng = location.longitude
            session[chat_id].state = "awaiting_end"
            session[chat_id].last_updated = time.time()
            await bot.send_message(chat_id, "Starting location received. Please send your destination location.")
            return {"status": "awaiting_end"}
        elif session[chat_id].state == "awaiting_end":
            end_lat = location.latitude
            end_lng = location.longitude
            session[chat_id].state = "completed"
            await bot.send_message(chat_id, "Destination location received. Calculating route...")
            
            graph = request.app.state.graph
            path = await find_shortest_path(graph, session[chat_id].start_lat, session[chat_id].start_lng, end_lat, end_lng)
            
            del session[chat_id]
            
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
    
    return {"status": "OK"}

@router.get("/crawl")
async def crawl():
    route_id = "66"
    direction = 1
    stop_id = "26"
    limit = 5
    results = await crawler.get_next_stops_prediction(route_id, direction, stop_id, limit)
    return {"results": results}

@router.get("/map-info")
async def get_map_info(request: Request):
    
    graph = request.app.state.graph
    
    if graph is None:
        return {"error": "Routing graph not loaded."}
    
    nodes_count = graph.number_of_nodes()
    edges_count = graph.number_of_edges()
    
    return {"nodes": nodes_count, "edges": edges_count}

@router.get("/test-route")
async def test_route(request: Request):
    graph = request.app.state.graph
    
    # start_lat, start_lng = 10.843006, 106.657168  # Gò Vấp
    # end_lat, end_lng = 10.759038, 106.682809  # Quận 5
    start_lat, start_lng = 10.727249, 106.607999
    end_lat, end_lng = 10.759038, 106.682809
    
    if graph is None:
        return {"error": "Routing graph not loaded."}
    
    start_time = time.perf_counter()
    path = await find_shortest_path(graph, start_lat, start_lng, end_lat, end_lng)
    
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
    
    end_time = time.perf_counter()
    print(f"Time taken to find path: {end_time - start_time:.2f} seconds")
    
    return {"geojson": geojson_route}