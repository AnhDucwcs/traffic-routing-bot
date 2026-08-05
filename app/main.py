import asyncio
import fastapi
from fastapi.staticfiles import StaticFiles
from cachetools import TTLCache
import psutil
import networkx as nx
import os
from loguru import logger
from app.api.routes import router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.routing.map_builder import load_routing_graph, load_segment_lengths
from app.services.routing.map_builder import load_route_stop_sequence, load_turn_penalties
from app.services.routing.map_builder import load_feather_data, load_edge_index
from app.services.routing.map_builder import load_stgcn_model, load_historical_baseline
from app.services.crawler.bus_crawler import BusCrawler
from app.services.crawler.scheduler import CrawlerScheduler
from app.services.routing.map_matching import MapMatcher
from app.services.routing.service import routing_service
from app.services.traffic_manager import TrafficManager
from app.services.storage.hot_storage import HotStorageManager
from app.services.storage.cold_storage import ColdStorageManager
from app.services.crowdsource import CrowdsourceManager

setup_logging()

# Hàm helper lấy RAM hiện tại của tiến trình (Process)
def get_current_ram_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

async def lifespan(app: fastapi.FastAPI):
    logger.info("Đang nạp Bản đồ vào RAM...")
    ram_before = get_current_ram_mb()  # Gọi một lần để log RAM trước khi nạp graph
    
    app.state.graph = load_routing_graph()
    
    logger.info("Đang tính toán Largest SCC để lọc đường chết...")
    largest_scc = set(max(nx.strongly_connected_components(app.state.graph), key=len))
    valid_edges = {(u, v) for u, v in app.state.graph.edges() if u in largest_scc and v in largest_scc}
    target_crs = app.state.graph.graph['crs']
    strtree, edge_ids, app.state.geom_dict = load_feather_data(target_crs)
    app.state.map_matcher = MapMatcher(strtree, edge_ids, app.state.geom_dict, valid_edges=valid_edges)
    
    turn_penalties = load_turn_penalties()
    edge_historical_baseline = load_historical_baseline()
    id_to_edge, edge_index, edge_weight = load_edge_index()
    model = load_stgcn_model(edge_index, edge_weight)
    app.state.traffic_manager = TrafficManager(app.state.graph, turn_penalties, edge_historical_baseline, id_to_edge, model)
    
    app.state.route_results = TTLCache(maxsize=1000, ttl=300)  
    
    app.state.hot_storage = HotStorageManager()
    
    app.state.cold_storage = ColdStorageManager(sync_interval_minutes=60)
    
    segment_lengths = load_segment_lengths()
    
    route_stop_sequence = load_route_stop_sequence()
    app.state.traffic_manager.build_index(segment_lengths)
    
    ram_after = get_current_ram_mb()  # Gọi một lần để log RAM sau khi nạp graph
    logger.info(f"Đã nạp Bản đồ vào RAM. RAM trước: {ram_before:.2f} MB, RAM sau: {ram_after:.2f} MB, Tăng thêm: {ram_after - ram_before:.2f} MB")

    # Create service instances and attach to app.state for DI
    app.state.routing_service = routing_service
    app.state.crawler = BusCrawler(segment_lengths, route_stop_sequence)

    # Start crawler scheduler
    await app.state.hot_storage.ensure_indexes()
    
    app.state.crowdsource_manager = CrowdsourceManager(
        hot_storage=app.state.hot_storage,
        map_matcher=app.state.map_matcher,
        traffic_manager=app.state.traffic_manager
    )
    await app.state.crowdsource_manager.ensure_indexes()
    
    app.state.crawler_scheduler = CrawlerScheduler(
        crawler=app.state.crawler,
        traffic_manager=app.state.traffic_manager,
        hot_storage=app.state.hot_storage,
        cold_storage=app.state.cold_storage,
        crowdsource_manager=app.state.crowdsource_manager
    )
    app.state.crawler_scheduler.start()

    yield

    logger.info("Shutting down application...")

    # Stop crawler scheduler and cleanup
    try:
        await app.state.crawler_scheduler.stop()
    except Exception:
        pass

    del app.state.graph
    del app.state.traffic_manager
    del app.state.route_results

app = fastapi.FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.include_router(router)