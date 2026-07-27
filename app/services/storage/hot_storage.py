import certifi
import asyncio
from app.core.logger import logger
from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError
from datetime import datetime
import pytz
import numpy as np
from bson.binary import Binary

class HotStorageManager:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client["traffic_db"]
        self.collection = self.db["bus_speeds"]

    async def ensure_indexes(self):
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
            ts = item.get("timestamp")
            try:
                dt_obj = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
            except ValueError:
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
    
    async def get_active_traffic_data(self):
        """Kéo toàn bộ dữ liệu kẹt xe còn hạn (chưa bị TTL xóa) từ MongoDB"""
        cursor = self.collection.find({})
        hot_data = []
        async for document in cursor:
            from_stop = document.get("from_stop_id")
            to_stop = document.get("to_stop_id")
            if from_stop and to_stop:
                hot_data.append({
                    "segment_id": f"{from_stop}_{to_stop}",
                    "speed_kmh": document.get("speed_kmh", 25.0)
                })
        return hot_data

    async def save_stgcn_history(self, history_buffer: list):
        """Lưu trữ lịch sử mảng traffic dưới dạng BSON Binary (siêu tốc, siêu nhẹ)."""
        if not history_buffer:
            return
        
        # history_buffer là 1 list các tuple (slot, np.ndarray). Chuyển chúng thành list dict.
        binary_frames = []
        for slot, arr in history_buffer:
            binary_frames.append({
                "slot": slot,
                "data": Binary(arr.tobytes())
            })
        
        try:
            await self.db["stgcn_history"].update_one(
                {"_id": "stgcn_history_doc"},
                {
                    "$set": {
                        "frames": binary_frames,
                        "updated_at": datetime.now(pytz.utc)
                    }
                },
                upsert=True
            )
            logger.info(f"[Hot DB] Đã lưu {len(history_buffer)} lớp lịch sử STGCN thành công.")
        except Exception as e:
            logger.error(f"[Hot DB] Lỗi khi lưu lịch sử STGCN: {e}")

    async def load_stgcn_history(self) -> list:
        """Kéo lịch sử traffic từ DB và chuyển đổi lại thành các mảng NumPy."""
        try:
            doc = await self.db["stgcn_history"].find_one({"_id": "stgcn_history_doc"})
            if not doc or "frames" not in doc:
                return []
            
            history_buffer = []
            for item in doc["frames"]:
                # Kiểm tra tương thích ngược nếu db cũ không có slot
                if isinstance(item, dict) and "slot" in item and "data" in item:
                    slot = item["slot"]
                    b = item["data"]
                else:
                    # Dữ liệu rác của phiên bản cũ, bỏ qua
                    continue
                    
                # Ép kiểu np.float32 giống dữ liệu khi thu thập (tốc độ xe)
                arr = np.frombuffer(b, dtype=np.float32)
                history_buffer.append((slot, arr))
            return history_buffer
        except Exception as e:
            logger.error(f"[Hot DB] Lỗi khi nạp lịch sử STGCN: {e}")
            return []