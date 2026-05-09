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
from tqdm.asyncio import tqdm
from httpx_socks import AsyncProxyTransport
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
            else:
                tqdm.write(f"[Radar] Trạm {stop_id} bị từ chối! Mã lỗi: {response.status_code}")
                
            if isinstance(data, list):
                for route in data:
                    route_id = route.get("r")
                    var_id = route.get("v")
                    active_buses = route.get("arrs", [])
                    
                    if (route_id is not None) and (var_id is not None) and len(active_buses) > 0:
                        # PHÁT HIỆN MỤC TIÊU! Ném vào Queue cho anh lính tỉa
                        await queue.put({
                            "route_id": str(route_id),
                            "variation_id": str(var_id),
                            "stop_id": str(stop_id)
                        })
        except Exception as e:
            tqdm.write(f"[Radar] Lỗi khi quét trạm {stop_id}: {type(e).__name__} - {str(e)}")
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
                    tqdm.write(f"[Lính Tỉa {worker_id}] Trạm gốc {stop_id} không có dữ liệu arrs, bỏ qua!")
                    continue # Nếu trạm gốc không có dữ liệu arrs thì bỏ qua luôn
                if not data[0].get("arrs"):
                    continue
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
            tqdm.write(f"[Lính Tỉa {worker_id}] Bắn trượt mục tiêu {route_id}-{var_id}-{stop_id}: {type(e).__name__} - {str(e)}")
            
        finally:
            # BÁO CÁO: Đã xử lý xong gói hàng này, Hộp thư có thể gạch tên nó
            queue.task_done()


# === 4. TƯỚNG CHỈ HUY CHIẾN DỊCH (MAIN ORCHESTRATOR) ===
async def run_campaign():
    tqdm.write(f"BẮT ĐẦU CHIẾN DỊCH QUÉT LÚC: {datetime.datetime.now()}")
    start_time = time.perf_counter()
    
    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(10)
    all_results = []
    
    try:
        curent_dir = Path(__file__).resolve().parent
        src_dir = curent_dir.parent
        file_fath = src_dir / "crawler" / "master_stops.json"
        with open(file_fath, "r", encoding="utf-8") as f:
            stops_data = json.load(f)
            stop_ids = [str(s["StopId"]) for s in stops_data if "StopId" in s]
    except Exception as e:
        tqdm.write(f"Lỗi đọc file: {e}")
        return
        
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Origin": "https://buyttphcm.com.vn",
        "Priority": "u=1, i",
        "Referer": "https://buyttphcm.com.vn/",
        "Sec-Ch-Ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Gpc": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }
    proxy_url = (settings.VN_PROXY or "").strip()
    client_kwargs = {
        "headers": headers,
        "timeout": 15.0,
        "http2": True,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    async with httpx.AsyncClient(**client_kwargs) as http_client:
        consumers = [asyncio.create_task(consumer_api_2(i, queue, http_client, all_results)) for i in range(20)]
            
        tqdm.write(f"Tung {len(stop_ids)} Radar...")
        producers = [producer_api_1(sid, queue, semaphore, http_client) for sid in stop_ids]
        await tqdm.gather(*producers)

        await queue.join()
        
        for c in consumers:
            c.cancel()
            
    if all_results:
        collection.insert_many(all_results)
        tqdm.write(f"Đã đổ {len(all_results)} kết quả vào MongoDB!")
    else:
        tqdm.write("Không thu hoạch được dữ liệu.")

    end_time = time.perf_counter()
    tqdm.write(f"Thời gian thực hiện chiến dịch: {end_time - start_time:.2f} giây")

# Không có while True, chạy 1 lần rồi thoát chương trình luôn
if __name__ == "__main__":
    asyncio.run(run_campaign())