import asyncio
from datetime import datetime
import gc
import pytz
from loguru import logger

class CrawlerScheduler:
    def __init__(self, crawler, traffic_manager, hot_storage, cold_storage, crowdsource_manager=None):
        self.crawler = crawler
        self.traffic_manager = traffic_manager
        self.hot_storage = hot_storage
        self.cold_storage = cold_storage
        self.crowdsource_manager = crowdsource_manager
        self._task = None
        self._stopped = asyncio.Event()
        self._last_sync_date = None
        
    async def _sync_morning_baseline(self):
        """Khôi phục baseline từ ổ cứng và đè báo cáo 7 ngày (Phase 1)"""
        if self.crowdsource_manager:
            try:
                seven_day_reports = await self.crowdsource_manager.get_historical_reports(days=7)
                await asyncio.to_thread(self.traffic_manager.sync_morning_baseline, seven_day_reports)
                logger.info("[Scheduler] Đã hoàn tất đồng bộ Baseline (Reset RAM & Đè 7 ngày).")
            except Exception as e:
                logger.error(f"[Scheduler] Lỗi khi đồng bộ Baseline: {e}")
        
    async def _update_hot_db(self, traffic_data):
        await asyncio.to_thread(self.traffic_manager.batch_apply_traffic_penalty, traffic_data)
    
    async def hydrate_ram(self):
        """Phục hồi dữ liệu kẹt xe từ MongoDB lên RAM khi khởi động"""
        try:
            if self.crowdsource_manager:
                await self._sync_morning_baseline()
            else:
                self.traffic_manager.reset_traffic()
                
            hot_data = await self.hot_storage.get_active_traffic_data()
            if hot_data:
                await self._update_hot_db(hot_data)
                logger.info(f"State Hydration: Đã phục hồi thần tốc {len(hot_data)} đoạn đường kẹt xe từ MongoDB vào RAM!")
            else:
                logger.info("Database trống, chờ đợt crawl đầu tiên...")
                
            if self.crowdsource_manager:
                recent_reports = await self.crowdsource_manager.get_recent_reports(minutes=45)
                if recent_reports:
                    await asyncio.to_thread(self.traffic_manager.apply_crowdsourced_overrides, recent_reports)
                    logger.info(f"State Hydration: Đã overlay {len(recent_reports)} báo cáo từ cộng đồng vào RAM!")
                
            history = await self.hot_storage.load_stgcn_history()
            if history:
                self.traffic_manager.history_buffer.clear()
                self.traffic_manager.history_buffer.extend(history)
                logger.info(f"State Hydration: Đã phục hồi {len(history)} khung lịch sử STGCN từ MongoDB!")
        except Exception as e:
            logger.error(f"Lỗi khi phục hồi RAM từ DB: {e}")

    async def _background_loop(self):
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        await self.hydrate_ram()
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
                        now_date = now_vn.date()
                        if self._last_sync_date != now_date:
                            if self.crowdsource_manager:
                                await self._sync_morning_baseline()
                            self._last_sync_date = now_date
                            
                        hot_data, cold_data = await self.crawler.run_campaign()
                        if hot_data:
                            await self.hot_storage.upsert_traffic_data(hot_data)
                            
                        # Luôn đồng bộ RAM với Hot DB để đào thải các đoạn đường hết hạn TTL
                        self.traffic_manager.reset_traffic()
                        active_hot_data = await self.hot_storage.get_active_traffic_data()
                        if active_hot_data:
                            await self._update_hot_db(active_hot_data)
                            logger.info(f"State Sync: Đã đồng bộ {len(active_hot_data)} đoạn đường kẹt xe từ MongoDB vào RAM!")
                        else:
                            logger.info("Tất cả dữ liệu đã hết hạn TTL, RAM đã được làm sạch.")

                        # Overlay Crowdsourced Reports
                        if self.crowdsource_manager:
                            recent_reports = await self.crowdsource_manager.get_recent_reports(minutes=45)
                            if recent_reports:
                                await asyncio.to_thread(self.traffic_manager.apply_crowdsourced_overrides, recent_reports)
                                logger.info(f"State Sync: Đã overlay {len(recent_reports)} báo cáo từ cộng đồng vào RAM!")

                        if cold_data:
                            await self.cold_storage.insert_historical_data(cold_data)
                        
                        # Task 4: Sao lưu lịch sử STGCN sau mỗi lần cào
                        if len(self.traffic_manager.history_buffer) > 0:
                            await self.hot_storage.save_stgcn_history(list(self.traffic_manager.history_buffer))
                            
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
