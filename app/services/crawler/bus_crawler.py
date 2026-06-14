import asyncio
import certifi
import datetime
import httpx
import json
import time
from numpy import random
from pathlib import Path
from pymongo import MongoClient
from app.core.config import settings
from app.core.logger import logger

class BusCrawler:
    def __init__(self, segment_lengths, route_stop_sequence):
        self.session = httpx.AsyncClient(timeout=10.0) 
        self.client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client["traffic_db"]
        self.collection = self.db["bus_speeds"]
        self.bus_states = {}
        self.segment_lengths = segment_lengths
        self.route_stop_sequence = route_stop_sequence


    async def producer_api_1(self, stop_id, queue, semaphore, http_client):
        """
        Nhiệm vụ: Quét trạm xem có xe buýt nào đang chuẩn bị tới không.
        Nếu có, nhét [route_id, variation_id, stop_id] vào Hộp thư (Queue).
        """
        async with semaphore:  # Bị chặn bởi Semaphore (chỉ cho phép 20 radar quét cùng lúc)
            for attempt in range(3):
                try:
                    url_api_1 = f"https://apicms.ebms.vn/prediction/predictbystopid/{stop_id}"
                    
                    timeout_config = httpx.Timeout(
                        connect=5.0, 
                        read=4.0, 
                        write=5.0, 
                        pool=5.0
                    )
                    response = await http_client.get(url_api_1, timeout=timeout_config)
                    
                    response.raise_for_status()

                    data = response.json()
                    crawled_time = datetime.datetime.now().isoformat()
                    if isinstance(data, list):
                        for route in data:
                            route_id = route.get("r")
                            var_id = route.get("v")
                            active_buses = route.get("arrs", [])
                            selected_buses = None
                            previous_stop_id = self.route_stop_sequence.get(f"{route_id}_{var_id}_{stop_id}")
                            
                            if not previous_stop_id:
                                continue
                            
                            segment_id = f"{previous_stop_id}_{stop_id}"
                            segment_length = self.segment_lengths.get(segment_id, {}).get("length_m")
                            
                            if not segment_length:
                                continue
                            
                            # Lấy các xe buýt gần nhất, tránh lấy các xe quá xa gây nhiễu dữ liệu
                            has_bus_nearby = False
                            for bus in active_buses:
                                d = float(bus.get("d", 0.0))
                                if 30 < d <= segment_length:  # Chỉ quan tâm xe buýt trong phạm vi độ dài segment
                                    has_bus_nearby = True
                                    selected_buses = bus
                                    break
                            
                            if (route_id is not None) and (var_id is not None) and has_bus_nearby:
                                # Nếu trạm này có xe buýt nào đang chuẩn bị tới, thì nhét thông tin vào Queue để Lính Tỉa bắn tiếp
                                await queue.put({
                                    "route_id": str(route_id),
                                    "variation_id": str(var_id),
                                    "stop_id": str(stop_id),
                                    "segment_id": segment_id,
                                    "segment_length": segment_length,
                                    "selected_bus": selected_buses,
                                    "crawled_time": crawled_time
                                })
                    break  # Nếu thành công thì thoát vòng retry
                except httpx.ReadTimeout:
                    logger.warning(f"Trạm {stop_id}: Proxy phản hồi quá chậm (ReadTimeout Lần {attempt + 1}/3).")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"[Radar] Lỗi khi quét trạm {stop_id}: {type(e).__name__} - {str(e)}")
                    break  # Với lỗi khác, không cần retry, thoát luôn
                    
            # CHỐNG BAN IP: Radar quét xong phải nghỉ ngơi một chút trước khi chuyển trạm
            await asyncio.sleep(random.uniform(0.05, 0.1))
    async def consumer_api_2(self, worker_id, queue, http_client, hot_results_dict, cold_results):
        while True:
            # Lấy mục tiêu từ Hộp thư (Nếu hộp thư trống, lính sẽ tự động đứng chờ)
            task = await queue.get()
            
            route_id = task["route_id"]
            var_id = task["variation_id"]
            stop_id = task["stop_id"]
            segment_id = task["segment_id"]
            current_stop_bus = task.get("selected_bus")
            crawled_time = task.get("crawled_time")
            instant_speed_kmh = float(current_stop_bus.get("s", 0.0))
            try:
                
                if current_stop_bus and segment_id:
                    if instant_speed_kmh < 80.0:
                        if instant_speed_kmh == 0.0 and current_stop_bus.get("d") <= 60.0:
                            # Xe buýt đang dừng đỗ tại trạm, không tính vào hot segment
                            pass
                        else:
                            if segment_id not in hot_results_dict:
                                hot_results_dict[segment_id] = []
                            hot_results_dict[segment_id].append({
                                "instant_speed_kmh": instant_speed_kmh,
                                "crawled_time": crawled_time
                            })
                
                url_api_2 = f"https://apicms.ebms.vn/prediction/{route_id}/{var_id}/{stop_id}/predictnextstops/1"
                response = await http_client.get(url_api_2)
                
                if response.status_code == 200:
                    data = response.json()
                    if not data or not isinstance(data, list) or not data[0].get("arrs"):
                        continue
                    buses = data[0]["arrs"]
                    next_stop_id = data[0].get("s")
                    crawl_time = datetime.datetime.now().isoformat()
                    next_stop_bus = None
                    
                    for bus in buses:
                        if bus.get("v") == current_stop_bus.get("v"):
                            next_stop_bus = bus
                            break
                    
                    if not next_stop_bus:
                        continue

                    
                    distance_to_current_stop = float(current_stop_bus.get("d", 0.0))
                    time_to_current_stop = float(current_stop_bus.get("t", 0.0))
                    distance_to_next_stop = float(next_stop_bus.get("d", 0.0))
                    time_to_next_stop = float(next_stop_bus.get("t", 0.0))
                        
                    cold_results.append({
                        "timestamp": crawl_time,
                        "route_id": str(route_id),
                        "var_id": str(var_id),
                        "vehicle_id": str(current_stop_bus.get("v")),
                        "to_current_stop_id": str(stop_id),
                        "to_next_stop_id": str(next_stop_id),
                        "distance_to_current_stop": round(distance_to_current_stop, 2),
                        "time_to_current_stop": round(time_to_current_stop, 2),
                        "distance_to_next_stop": round(distance_to_next_stop, 2),
                        "time_to_next_stop": round(time_to_next_stop, 2),
                        "instant_speed_kmh": instant_speed_kmh,
                    })
                    
            except Exception as e:
                logger.error(f"[Lính Tỉa {worker_id}] Bắn trượt mục tiêu (route_id={route_id}, var_id={var_id}, stop_id={stop_id})")

            finally:
                queue.task_done()

    async def run_campaign(self):
        logger.info(f"BẮT ĐẦU CHIẾN DỊCH QUÉT LÚC: {datetime.datetime.now()}")
        start_time = time.perf_counter()
        
        queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(15)
        hot_results_dict = {}
        cold_results = []
        
        try:
            curent_dir = Path(__file__).resolve().parent
            base_dir = curent_dir.parent.parent.parent
            file_fath = base_dir / "data" / "master_stops.json"
            with open(file_fath, "r", encoding="utf-8") as f:
                stops_data = json.load(f)
                stop_ids = [str(s["StopId"]) for s in stops_data if "StopId" in s]
        except Exception as e:
            logger.error(f"Lỗi đọc file: {e}")
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
            consumers = [asyncio.create_task(self.consumer_api_2(i, queue, http_client, hot_results_dict, cold_results)) for i in range(10)]
            total_stops = len(stop_ids)
            completed = 0
            next_log_pct = 10.0    
            logger.info(f"Tung {len(stop_ids)} Radar...")
            producer_tasks = [asyncio.create_task(self.producer_api_1(sid, queue, semaphore, http_client)) for sid in stop_ids]
            for task in asyncio.as_completed(producer_tasks):
                await task
                completed += 1
                progress_pct = (completed / total_stops) * 100 if total_stops else 100.0

                # Log khi đạt mỗi mốc 10% hoặc khi hoàn tất trạm cuối
                if progress_pct >= next_log_pct or completed == total_stops:
                    logger.info(
                        f"Tiến độ quét trạm: {completed}/{total_stops} ({progress_pct:.1f}%)"
                    )
                    while next_log_pct <= progress_pct and next_log_pct < 100:
                        next_log_pct += 10.0
            
            await queue.join() # Đợi cho đến khi tất cả các mục tiêu trong Queue được xử lý xong
            for c in consumers:
                c.cancel()
        hot_results = []
        
        for seg_id, records in hot_results_dict.items():
            average_speed = sum(r["instant_speed_kmh"] for r in records) / len(records)
            if average_speed < 5.0:
                average_speed = 5.0
            latest_timestamp = max(x["crawled_time"] for x in records)
            hot_results.append({
                "segment_id": seg_id,
                "speed_kmh": round(average_speed, 2),
                "timestamp": latest_timestamp,
            })
            
        if hot_results or cold_results:
            logger.info(f"Đã thu hoạch xong: Hot results: {len(hot_results)}, Cold results: {len(cold_results)}")
        else:
            logger.info("Không thu hoạch được dữ liệu nào trong chiến dịch này.")

        end_time = time.perf_counter()
        logger.info(f"Thời gian thực hiện chiến dịch: {end_time - start_time:.2f} giây")
        return hot_results, cold_results
