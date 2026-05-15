import asyncio
from datetime import datetime
from cachetools import TTLCache
import fastapi
from contextlib import asynccontextmanager

import pytz
from app.api.routes import router
from app.core.config import settings
from app.services.routing.map_builder import load_routing_graph
from app.services.crawler.bus_crawler import crawler

async def lifespan(app: fastapi.FastAPI):   
    print("Đang nạp Bản đồ vào RAM...")
    app.state.graph = load_routing_graph()
    app.state.user_sessions = TTLCache(maxsize=10000, ttl=300)  # Cache with max 10000 items, each valid for 5 minutes
    
    print("Đang khởi động Crawler chạy ngầm...")
    crawler_task = asyncio.create_task(crawler_background_task())

    yield
    
    print("Shutting down application...")
    
    crawler_task.cancel()
    del app.state.graph
    app.state.user_sessions.clear()

async def crawler_background_task():   
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    try:
        while True:
            now_vn = datetime.now(vn_tz)
            current_hour = now_vn.hour
            should_crawl = False
            
            if 22 <= current_hour <= 23 or 0 <= current_hour < 4:
                sleep_time = 3600 # short sleep for heartbeat during all-night hours
            elif current_hour in [6, 7, 8, 16, 17, 18]:
                sleep_time = 300 # 5 minutes during rush hours
                should_crawl = True
            else:
                sleep_time = 1200 # 20 minutes during off-peak hours
                should_crawl = True
            
            if should_crawl:
                try: await crawler.run_campaign()
                except Exception as e:
                    print(f"❌ Lỗi mẻ cào này: {e}. Vẫn sống, đợi mẻ sau cào tiếp!")
            
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print("🛑 Nhận lệnh Shutdown! Đã dừng crawler an toàn.")
        # Dọn dẹp tài nguyên của crawler nếu cần

app = fastapi.FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.include_router(router)