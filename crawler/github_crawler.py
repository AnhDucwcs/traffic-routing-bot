import os
import asyncio
import httpx
import json
import random
import datetime
from pymongo import MongoClient
import certifi
import time
from pathlib import Path
from app.core.config import settings


client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
db = client["traffic_db"]
collection = db["bus_speeds"]

# === 2. TẠO TRẠM RADAR (PRODUCER) ===
async def producer_api_1(stop_id, queue, semaphore, http_client):
    """
    Nhiệm vụ: Quét trạm xem có xe buýt nào đang chuẩn bị tới không.
    Nếu có, nhét [route_id, variation_id, stop_id] vào Hộp thư (Queue).
    """
    async with semaphore:  # Bị chặn bởi Semaphore (chỉ cho phép 20 radar quét cùng lúc)
        try:
            # TODO: THAY URL VÀ LOGIC DƯỚI ĐÂY BẰNG API 1 MÀ BẠN VỪA TÌM ĐƯỢC
            url_api_1 = f"https://apicms.ebms.vn/prediction/predictbystopid/{stop_id}" # <--- SỬA URL NÀY
            
            response = await http_client.get(url_api_1)

            if response.status_code == 200:
                data = response.json()
                
                
                if isinstance(data, list):
                    for route in data:
                        route_id = route.get("r")
                        var_id = route.get("v")
                        active_buses = route.get("arrs", [])
                        
                        if route_id and var_id and len(active_buses) > 0:
                            # PHÁT HIỆN MỤC TIÊU! Ném vào Queue cho anh lính tỉa
                            await queue.put({
                                "route_id": str(route_id),
                                "variation_id": str(var_id),
                                "stop_id": str(stop_id)
                            })
        except Exception as e:
            pass # Nuốt lỗi để radar không bị sập khi quét trạm khác
            
        finally:
            # CHỐNG BAN IP: Radar quét xong phải nghỉ ngơi một chút trước khi chuyển trạm
            await asyncio.sleep(random.uniform(0.1, 0.3))


# === 3. TẠO ĐỘI BẮN TỈA (CONSUMER) ===
async def consumer_api_2(worker_id, queue, http_client, all_results):
    """
    Nhiệm vụ: Canh me Hộp thư. Hễ có tọa độ là rút súng bắn API 2, tính Vận tốc, gom vào bao tải.
    """
    while True:
        # Lấy mục tiêu từ Hộp thư (Nếu hộp thư trống, lính sẽ tự động đứng chờ)
        task = await queue.get()
        
        route_id = task["route_id"]
        var_id = task["variation_id"]
        stop_id = task["stop_id"]
        
        try:
            # API 2: Tính toán dự báo 5 trạm tiếp theo
            url_api_2 = f"https://apicms.ebms.vn/prediction/{route_id}/{var_id}/{stop_id}/predictnextstops/5"
            response = await http_client.get(url_api_2)
            
            if response.status_code == 200:
                data = response.json()
                if not data or not data[0].get("arrs"):
                    continue # Nếu trạm gốc không có dữ liệu arrs thì bỏ qua luôn
                # Bưng nguyên logic tính vận tốc cực xịn của bạn vào đây
                if data and isinstance(data, list) and len(data) > 0:
                    try:
                        base_d = data[0]["arrs"][0]["d"]
                        base_t = data[0]["arrs"][0]["t"]
                        crawl_time = datetime.datetime.now()

                        for i in range(1, len(data)):
                            if len(data[i].get("arrs", [])) == 0:
                                continue
                            
                            curent_d = data[i]["arrs"][0]["d"]
                            curent_t = data[i]["arrs"][0]["t"]
                            next_stop_id = str(data[i].get("s") or "")
                            
                            detal_d = curent_d - base_d
                            detal_t = curent_t - base_t
                            
                            if detal_d > 0 and detal_t > 0:
                                v_ms = detal_d / detal_t
                                all_results.append({
                                    "next_stop_id": next_stop_id,
                                    "speed_ms": round(v_ms, 2),
                                    "timestamp": crawl_time
                                })
                            
                            base_d = curent_d
                            base_t = curent_t
                    except (IndexError, KeyError):
                        pass # Nếu trạm không có dữ liệu arrs thì bỏ qua
                        
        except Exception as e:
            print(f"[Lính Tỉa {worker_id}] Bắn trượt mục tiêu {route_id}-{var_id}-{stop_id}: {e}")
            
        finally:
            # BÁO CÁO: Đã xử lý xong gói hàng này, Hộp thư có thể gạch tên nó
            queue.task_done()


# === 4. TƯỚNG CHỈ HUY CHIẾN DỊCH (MAIN ORCHESTRATOR) ===
async def run_campaign():
    print(f"BẮT ĐẦU CHIẾN DỊCH QUÉT LÚC: {datetime.datetime.now()}")
    
    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(20)
    all_results = []
    
    try:
        curent_dir = Path(__file__).resolve().parent
        src_dir = curent_dir.parent
        file_fath = src_dir / "crawler" / "master_stops.json"
        with open(file_fath, "r", encoding="utf-8") as f:
            stops_data = json.load(f)
            stop_ids = [str(s["StopId"]) for s in stops_data if "StopId" in s]
    except Exception as e:
        print("Lỗi đọc file:", e)
        return
        
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as http_client:
        consumers = [asyncio.create_task(consumer_api_2(i, queue, http_client, all_results)) for i in range(20)]
            
        print(f"📡 Tung {len(stop_ids)} Radar...")
        producers = [producer_api_1(sid, queue, semaphore, http_client) for sid in stop_ids]
        await asyncio.gather(*producers)

        await queue.join()
        
        for c in consumers:
            c.cancel()
            
    if all_results:
        collection.insert_many(all_results)
        print(f"Đã đổ {len(all_results)} kết quả vào MongoDB!")
    else:
        print("Không thu hoạch được dữ liệu.")

# Không có while True, chạy 1 lần rồi thoát chương trình luôn
if __name__ == "__main__":
    asyncio.run(run_campaign())