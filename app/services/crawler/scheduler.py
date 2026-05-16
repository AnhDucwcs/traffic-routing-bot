import asyncio
from datetime import datetime
import gc
import pytz
from loguru import logger


class CrawlerScheduler:
    def __init__(self, crawler):
        self.crawler = crawler
        self._task = None
        self._stopped = asyncio.Event()

    async def _background_loop(self):
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        try:
            while True:
                now_vn = datetime.now(vn_tz)
                current_hour = now_vn.hour
                should_crawl = False

                if 22 <= current_hour <= 23 or 0 <= current_hour < 4:
                    sleep_time = 3600
                elif current_hour in [6, 7, 8, 16, 17, 18]:
                    sleep_time = 300
                    should_crawl = True
                else:
                    sleep_time = 1200
                    should_crawl = True

                if should_crawl:
                    try:
                        await self.crawler.run_campaign()
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
