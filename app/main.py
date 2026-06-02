import asyncio
import fastapi
from fastapi.staticfiles import StaticFiles
import psutil
import os
from loguru import logger
from app.api.routes import router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.routing.map_builder import load_routing_graph, load_segment_lengths
from app.services.crawler.bus_crawler import BusCrawler
from app.services.crawler.scheduler import CrawlerScheduler
from app.services.routing.service import routing_service
from app.services.traffic_manager import TrafficManager

setup_logging()

# Hàm helper lấy RAM hiện tại của tiến trình (Process)
def get_current_ram_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

async def lifespan(app: fastapi.FastAPI):
    logger.info("Đang nạp Bản đồ vào RAM...")
    ram_before = get_current_ram_mb()  # Gọi một lần để log RAM trước khi nạp graph
    app.state.graph = load_routing_graph()
    app.state.traffic_manager = TrafficManager(app.state.graph)
    segment_lengths = load_segment_lengths()
    app.state.traffic_manager.build_index(segment_lengths)
    ram_after = get_current_ram_mb()  # Gọi một lần để log RAM sau khi nạp graph
    logger.info(f"Đã nạp Bản đồ vào RAM. RAM trước: {ram_before:.2f} MB, RAM sau: {ram_after:.2f} MB, Tăng thêm: {ram_after - ram_before:.2f} MB")

    # Create service instances and attach to app.state for DI
    app.state.routing_service = routing_service
    app.state.crawler = BusCrawler()

    # Start crawler scheduler
    app.state.crawler_scheduler = CrawlerScheduler(app.state.crawler)
    app.state.crawler_scheduler.start()

    yield

    logger.info("Shutting down application...")

    # Stop crawler scheduler and cleanup
    try:
        await app.state.crawler_scheduler.stop()
    except Exception:
        pass

    del app.state.graph


app = fastapi.FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.include_router(router)
app.mount("/app", StaticFiles(directory="app/static"), name="static")