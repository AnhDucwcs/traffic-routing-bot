import os
import sys
import pickle
import asyncio
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from collections import defaultdict
from app.core.config import settings

# Setup paths
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(SRC_DIR))


MONGO_URI = settings.MONGO_URI
DB_NAME = "traffic_db"
BASELINE_PATH = SRC_DIR / "data" / "edge_historical_baseline.pkl"

ALPHA = 0.9  # Trọng số cho Phase 1 (90% báo cáo thực tế, 10% baseline cũ)

async def main():
    print("Bắt đầu phân tích báo cáo giao thông từ người dùng...")
    
    # 1. Kết nối MongoDB
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    # 2. Lấy các reports chưa xử lý
    cursor = db.traffic_reports.find({"processed": {"$ne": True}})
    reports = await cursor.to_list(length=None)
    
    if not reports:
        print("Không có báo cáo mới nào cần xử lý. Thoát script.")
        return
        
    print(f"Tìm thấy {len(reports)} báo cáo mới.")
    
    # 3. Tải Baseline cũ
    edge_baseline = {}
    if BASELINE_PATH.exists():
        with open(BASELINE_PATH, 'rb') as f:
            edge_baseline = pickle.load(f)
        print(f"Đã tải {len(edge_baseline):,} records từ baseline hiện tại.")
    else:
        print("Không tìm thấy file baseline cũ. Hãy tạo một file baseline mới.")
        return
        
    # 4. Phân loại và Gom nhóm
    market_edges = set()
    grouped_reports = defaultdict(list)
    
    for rep in reports:
        u, v = rep['u'], rep['v']
        severity = rep.get('severity', '')
        
        if severity == 'market':
            market_edges.add((u, v))
        else:
            day_type = rep.get('day_type', 1)
            time_slot = rep.get('time_slot', 0)
            speed = rep['speed_kmh']
            grouped_reports[(u, v, day_type, time_slot)].append(speed)
        
    # 5. Phân tích và Cập nhật
    updates_count = 0
    new_records_count = 0
    
    # 5.1 Ghi đè Hẻm Chợ vĩnh viễn (market)
    for (u, v) in market_edges:
        for day in [1, 2, 3]:
            for t in range(96):
                key = (u, v, day, t)
                if key not in edge_baseline:
                    new_records_count += 1
                else:
                    updates_count += 1
                edge_baseline[key] = 1.0
                
    # 5.2 Xử lý các báo cáo kẹt xe tạm thời
    for key, speeds in grouped_reports.items():
        if (key[0], key[1]) in market_edges:
            continue  # Đã bị khóa là chợ, bỏ qua báo cáo thường
            
        avg_reported_speed = sum(speeds) / len(speeds)
        u, v, day_type, time_slot = key
        
        if key in edge_baseline:
            old_speed = edge_baseline[key]
            # Exponential Moving Average (EMA) - blend giữa cũ và mới
            new_speed = (1 - ALPHA) * old_speed + ALPHA * avg_reported_speed
            edge_baseline[key] = new_speed
            updates_count += 1
            
            # Temporal slope: ±1=70%, ±2=30%
            delta = old_speed - new_speed
            if delta > 0:
                for ns, r in ((-1, 0.7), (1, 0.7),
                              (-2, 0.3), (2, 0.3)):
                    s = time_slot + ns
                    if 0 <= s < 96:
                        nk = (u, v, day_type, s)
                        n_old = edge_baseline.get(
                            nk, old_speed
                        )
                        bl = n_old - delta * r
                        if bl < n_old:
                            edge_baseline[nk] = max(
                                bl, 1.0
                            )
        else:
            # Chưa từng có trong lịch sử thì lấy thẳng
            edge_baseline[key] = avg_reported_speed
            new_records_count += 1
            
    # 6. Lưu file Pickle
    with open(BASELINE_PATH, 'wb') as f:
        pickle.dump(edge_baseline, f)
        
    print(f"Đã lưu baseline mới với {len(edge_baseline):,} records tổng cộng.")
    print(f"   - Cập nhật {updates_count} records cũ")
    print(f"   - Thêm mới {new_records_count} records")
    
    # 7. Đánh dấu đã xử lý trong DB
    report_ids = [rep['_id'] for rep in reports]
    result = await db.traffic_reports.update_many(
        {"_id": {"$in": report_ids}},
        {"$set": {"processed": True}}
    )
    print(f"Đã đánh dấu {result.modified_count} báo cáo thành 'processed' trong DB.")
    print("Hoàn tất!")

if __name__ == "__main__":
    asyncio.run(main())
