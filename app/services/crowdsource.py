from datetime import datetime, timezone
import pytz
from app.models.schemas import ReportRequest
from app.core.logger import logger
from fastapi import HTTPException
from cachetools import TTLCache
import asyncio

class CrowdsourceManager:
    def __init__(self, hot_storage, map_matcher, traffic_manager):
        self.db = hot_storage.db
        self.map_matcher = map_matcher
        self.traffic_manager = traffic_manager
        self.to_graph = traffic_manager.to_graph
        self.rate_limit = TTLCache(maxsize=5000, ttl=300) # 5 phút block spam mỗi user

    async def ensure_indexes(self):
        try:
            # Tạo index cho created_at nhưng KHÔNG TTL (vì muốn lưu vĩnh viễn cho offline script)
            await self.db.traffic_reports.create_index("created_at")
            logger.info("[Crowdsource] Đã tạo index cho traffic_reports")
        except Exception as e:
            logger.error(f"[Crowdsource] Lỗi tạo index: {e}")

    async def report_jam(self, request: ReportRequest):
        # 1. Rate limiting
        user_key = str(request.user_id)
        if user_key in self.rate_limit:
            raise HTTPException(status_code=429, detail="Vui lòng chờ 5 phút trước khi báo cáo tiếp.")
            
        # 2. Transform tọa độ
        if self.to_graph:
            x, y = self.to_graph.transform(request.lng, request.lat)
        else:
            x, y = request.lng, request.lat
            
        # 3. Snap to edge
        try:
            u, v, k, px, py, dist = self.map_matcher.snap_to_edge(x, y, max_dist_m=50.0)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Bạn không ở gần đường lộ (khoảng cách > 50m).")
            
        if request.severity == "market":
            # Biện pháp bảo vệ: Không cho phép đánh dấu Hẻm Chợ trên các đường lớn
            edge_data = self.traffic_manager.G.get_edge_data(u, v, k)
            if edge_data:
                highway = edge_data.get('highway', '')
                if highway in ['primary', 'primary_link', 'secondary', 'secondary_link', 'trunk', 'trunk_link']:
                    raise HTTPException(status_code=400, detail="Không thể báo cáo Hẻm Chợ trên đường lớn.")
            speed_kmh = 1.0
        elif request.severity == "congested":
            speed_kmh = 15.0
        else:
            speed_kmh = 5.0
        
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now_vn = datetime.now(vn_tz)
        time_slot = (now_vn.hour * 60 + now_vn.minute) // 15
        day_type = 1 if now_vn.weekday() < 4 else (2 if now_vn.weekday() == 4 else 3)
        
        report_doc = {
            "user_id": user_key,
            "u": int(u),
            "v": int(v),
            "k": int(k),
            "severity": request.severity,
            "speed_kmh": speed_kmh,
            "lat": request.lat,
            "lng": request.lng,
            "time_slot": time_slot,
            "day_type": day_type,
            "created_at": datetime.now(timezone.utc)
        }
        
        # 4. Ghi DB
        await self.db.traffic_reports.insert_one(report_doc)
        self.rate_limit[user_key] = True
        
        # 5. Ghi đè RAM (sẽ gọi traffic_manager.apply_crowdsourced_overrides)
        report_obj = {
            "u": int(u),
            "v": int(v),
            "k": int(k),
            "speed_kmh": speed_kmh
        }
        await asyncio.to_thread(self.traffic_manager.apply_crowdsourced_overrides, [report_obj])
        
        logger.info(f"[Crowdsource] User {user_key} báo {request.severity} tại ({u}, {v}, {k}) - {speed_kmh}km/h")
        
        return {
            "status": "success",
            "message": "Đã ghi nhận báo cáo giao thông",
            "edge": [int(u), int(v), int(k)],
            "speed_applied": float(speed_kmh)
        }

    async def get_recent_reports(self, minutes: int = 45):
        """Lấy các reports được báo cáo trong vòng `minutes` phút qua"""
        from datetime import timedelta
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        
        cursor = self.db.traffic_reports.find({"created_at": {"$gte": cutoff_time}})
        reports = []
        async for doc in cursor:
            reports.append({
                "u": doc["u"],
                "v": doc["v"],
                "k": doc["k"],
                "speed_kmh": doc["speed_kmh"]
            })
        return reports

    async def get_historical_reports(self, days: int = 7):
        """Lấy các reports trong vòng 7 ngày qua, nhóm theo (u, v, day_type, time_slot) và tính trung bình tốc độ"""
        from datetime import timedelta
        from collections import defaultdict
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = self.db.traffic_reports.find({"created_at": {"$gte": cutoff_time}})
        
        grouped = defaultdict(list)
        async for doc in cursor:
            u, v = doc.get("u"), doc.get("v")
            day_type = doc.get("day_type")
            time_slot = doc.get("time_slot")
            speed = doc.get("speed_kmh")
            if None not in (u, v, day_type, time_slot, speed):
                grouped[(u, v, day_type, time_slot)].append(speed)
                
        results = []
        for (u, v, day_type, time_slot), speeds in grouped.items():
            avg_speed = sum(speeds) / len(speeds)
            results.append({
                "u": u,
                "v": v,
                "day_type": day_type,
                "time_slot": time_slot,
                "speed_kmh": avg_speed
            })
            
        return results
