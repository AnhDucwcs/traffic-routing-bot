import certifi
import asyncio
from app.core.logger import logger
from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError
from datetime import datetime
import pytz

class HotStorageManager:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client["traffic_db"]
        self.collection = self.db["bus_speeds"]
        self._ensure_indexes()

    async def _ensure_indexes(self):
        try:
            # 1. Compound Index
            await self.collection.create_index(
                [("from_stop_id", ASCENDING), ("to_stop_id", ASCENDING)],
                unique=True,
                name="idx_segment_unique"
            )
            
            # 2. TTL Index
            await self.collection.create_index(
                "timestamp",
                expireAfterSeconds=3600,
                name="idx_ttl_timestamp"
            )
            logger.info("[Hot DB] Đã kiểm tra/khởi tạo Index thành công.")
        except Exception as e:
            logger.error(f"[Hot DB] Lỗi khi tạo Index: {e}")

    async def upsert_traffic_data(self, hot_data: list):
        """Nhận danh sách dữ liệu và ghi đè vào MongoDB (Non-blocking)"""
        if not hot_data:
            return

        if not hot_data:
            return

        operations = []
        
        for item in hot_data:
            # Tách segment_id ra lại thành 2 node
            segment_id = item.get("segment_id", "")
            if "_" in segment_id:
                from_stop, to_stop = segment_id.split("_", 1)
            else:
                from_stop = item.get("from_stop_id")
                to_stop = item.get("to_stop_id")

            # Chốt chặn bảo vệ dữ liệu rác
            if not from_stop or not to_stop:
                continue

            speed_kmh = item.get("speed_kmh", 0.0)
            
            # Đồng nhất kiểu dữ liệu datetime object cho TTL Index
            timestamp_str = item.get("timestamp")
            try:
                if isinstance(timestamp_str, str):
                    dt_obj = datetime.fromisoformat(timestamp_str)
                elif isinstance(timestamp_str, datetime):
                    dt_obj = timestamp_str
                else:
                    dt_obj = datetime.now(pytz.UTC)
            except Exception:
                dt_obj = datetime.now(pytz.UTC)

            filter_query = {
                "from_stop_id": from_stop,
                "to_stop_id": to_stop
            }
            
            update_doc = {
                "$set": {
                    "speed_kmh": speed_kmh,
                    "timestamp": dt_obj
                }
            }
                # Tạo lệnh UPSERT: Có thì ghi đè, chưa có thì tạo mới
            operations.append(UpdateOne(filter_query, update_doc, upsert=True))

        # Thực thi một lần (Batch) để tối ưu I/O
        if operations:
            try:
                # ordered=False giúp nếu 1 dòng lỗi, các dòng khác vẫn được ghi tiếp
                result = await self.collection.bulk_write(operations, ordered=False)
                logger.info(f"[Hot DB] Hoàn tất: Tạo mới {result.upserted_count}, Cập nhật {result.modified_count} đoạn đường.")
            except BulkWriteError as bwe:
                logger.error(f"[Hot DB] Lỗi khi ghi hàng loạt: {bwe.details}")
            except Exception as e:
                logger.error(f"[Hot DB] Lỗi kết nối hoặc thực thi Database: {e}")