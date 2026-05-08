from fastapi import APIRouter, Request
from rich import text
from app.models import request_models
from app.services.telegram_bot import bot
from app.services.crawler.bus_crawler import crawler
from app.services.routing.pathfinder import find_shortest_path
import time
from pyproj import Transformer

router = APIRouter()

@router.get("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/webhook")
async def handle_webhook(update: request_models.TelegramUpdate):
    if update.message:
        chat_id = update.message.chat.id
        text = update.message.text
    elif update.edited_message:
        chat_id = update.edited_message.chat.id
        text = update.edited_message.text
    else:
        print("Update does not support")
        return {"status": "unsupported update type", "update_id": update.update_id}
    if text:
        await bot.send_message(chat_id, f"Received your message: {text}")
    else:
        await bot.send_message(chat_id, "Received your message, but it has no text.")
    return {"status": "received", "update_id": update.update_id}

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