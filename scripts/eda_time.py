from pathlib import Path
import sys

from pymongo import MongoClient
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings

# 1. Kết nối Database
client = MongoClient(settings.MONGO_URI)
db = client["traffic_db"]        # Sửa lại tên DB cho đúng
collection = db["bus_speeds"]    # Sửa lại tên Collection cho đúng

print("Đang nhờ MongoDB phân tích 1.1 triệu dòng... Hãy kiên nhẫn...")

# 2. Dùng Aggregation Pipeline (Tuyệt chiêu của NoSQL) để đếm số lượng data theo từng GIỜ
pipeline = [
    {
        # Giả sử trường lưu thời gian của bạn tên là "timestamp" hoặc "created_at" (Sửa lại cho đúng)
        "$project": {
            "hour": {"$hour": "$timestamp"} # Trích xuất giờ (0-23) từ timestamp
        }
    },
    {
        "$group": {
            "_id": "$hour",
            "count": {"$sum": 1}
        }
    },
    {
        "$sort": {"_id": 1} # Sắp xếp từ 0h đến 23h
    }
]

results = list(collection.aggregate(pipeline))

# 3. Trích xuất dữ liệu để vẽ
hours = [res["_id"] for res in results]
counts = [res["count"] for res in results]

# 4. Vẽ biểu đồ Histogram (Cột)
plt.figure(figsize=(10, 6))
plt.bar(hours, counts, color='skyblue', edgecolor='black')
plt.title("Phân bố Dữ liệu Giao thông theo Khung Giờ", fontsize=16)
plt.xlabel("Giờ trong ngày (0 - 23)", fontsize=12)
plt.ylabel("Số lượng bản ghi", fontsize=12)
plt.xticks(range(0, 24))
plt.grid(axis='y', linestyle='--', alpha=0.7)

# In số liệu ra màn hình
print("Dữ liệu chi tiết:")
for h, c in zip(hours, counts):
    print(f"Giờ {h}h: {c} bản ghi")

output_path = Path(__file__).resolve().with_name("eda_time.png")
plt.savefig(output_path, dpi=150, bbox_inches="tight")
plt.close()

print(f"Đã lưu biểu đồ tại: {output_path}")