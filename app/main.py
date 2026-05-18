import asyncio
import fastapi
from loguru import logger
from app.api.routes import router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.routing.map_builder import load_routing_graph
from app.services.bot_adapter import BotAdapter
from app.services.crawler.bus_crawler import BusCrawler
from app.services.crawler.scheduler import CrawlerScheduler
from app.services.routing.service import routing_service
from app.core.state import init_app_state, shutdown_app_state

setup_logging()


async def lifespan(app: fastapi.FastAPI):
    logger.info("Đang nạp Bản đồ vào RAM...")
    app.state.graph = load_routing_graph()

    # Initialize shared application state (user sessions + locks)
    init_app_state(app, maxsize=10000, ttl=300)

    # Create service instances and attach to app.state for DI
    app.state.routing_service = routing_service
    app.state.crawler = BusCrawler()
    bot_task = asyncio.create_task(BotAdapter(app).start_telegram_bot(user_sessions=app.state.user_sessions, graph=app.state.graph))

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

    try:
        bot_task.cancel()
    except Exception:
        pass

    shutdown_app_state(app)
    del app.state.graph


app = fastapi.FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.include_router(router)