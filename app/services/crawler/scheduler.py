import asyncio
from datetime import datetime
import gc
import pytz
from loguru import logger


class CrawlerScheduler:
    def __init__(self, crawler, traffic_manager, hot_storage, cold_storage):
        self.crawler = crawler
        self.traffic_manager = traffic_manager
        self.hot_storage = hot_storage
        self.cold_storage = cold_storage
        self._task = None
        self._stopped = asyncio.Event()
        
    def _update_hot_db(self, traffic_data):
        for item in traffic_data:
            speed = item['speed_kmh']
            segment_id = item['segment_id']
            
            penalty = 1.0
            if speed < 5.0:
                penalty = 5.0
            elif speed < 10.0:
                penalty = 2.5
            elif speed < 15.0:
                penalty = 1.5
                
            self.traffic_manager.apply_traffic_penalty(segment_id, penalty)

    async def _background_loop(self):
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        try:
            while True:
                now_vn = datetime.now(vn_tz)
                current_hour = now_vn.hour
                current_minute = now_vn.minute
                should_crawl = False

                if (current_hour == 21 and current_minute > 30) or (22 <= current_hour <= 23) or (0 <= current_hour < 5) or (current_hour == 5 and current_minute < 30):
                    sleep_time = 1800
                elif current_hour in [6, 7, 8, 16, 17, 18]:
                    sleep_time = 120
                    should_crawl = True
                else:
                    sleep_time = 300
                    should_crawl = True

                if should_crawl:
                    try:
                        hot_data, cold_data = await self.crawler.run_campaign()
                        if hot_data:
                            await self.hot_storage.upsert_traffic_data(hot_data)
                            self._update_hot_db(hot_data)
                            logger.info(f"Đã cập nhật {len(hot_data)} đoạn đường kẹt xe vào Hot Storage & RAM.")
                        if cold_data:
                            await self.cold_storage.insert_historical_data(cold_data)
                        gc.collect()
                    except Exception as e:
                        logger.exception(f"Lỗi lần cào dữ liệu này: {e}.")

                await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            logger.info("Ngừng crawler background task...")
            return

    def start(self, loop=None):
        if self._task is not None and not self._task.done():
            return
        loop = loop or asyncio.get_event_loop()
        self._task = loop.create_task(self._background_loop())
        return self._task

    async def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
