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
    def __init__(self):
        self.session = httpx.AsyncClient(timeout=10.0) 
        self.client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client["traffic_db"]
        self.collection = self.db["bus_speeds"]


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

                    if isinstance(data, list):
                        for route in data:
                            route_id = route.get("r")
                            var_id = route.get("v")
                            active_buses = route.get("arrs", [])
                            
                            if (route_id is not None) and (var_id is not None) and len(active_buses) > 0:
                                # Nếu trạm này có xe buýt nào đang chuẩn bị tới, thì nhét thông tin vào Queue để Lính Tỉa bắn tiếp
                                await queue.put({
                                    "route_id": str(route_id),
                                    "variation_id": str(var_id),
                                    "stop_id": str(stop_id)
                                })
                    break  # Nếu thành công thì thoát vòng retry
                except httpx.ReadTimeout:
                    logger.warning(f"Trạm {stop_id}: Proxy phản hồi quá chậm (ReadTimeout Lần {attempt + 1}/3).")
                    await asyncio.sleep(1)
                except httpx.RemoteProtocolError:
                    logger.warning(f"Trạm {stop_id}: Server cắt kết nối HTTP/2 (Lần {attempt + 1}/3). Đợi 1s...")
                    await asyncio.sleep(1)
                except httpx.HTTPError as e:
                    logger.warning(f"Trạm {stop_id}: Lỗi HTTP {e.response.status_code if e.response else 'N/A'} (Lần {attempt + 1}/3). Đợi 1s...")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"[Radar] Lỗi khi quét trạm {stop_id}: {type(e).__name__} - {str(e)}")
                    break  # Với lỗi khác, không cần retry, thoát luôn
                    
            # CHỐNG BAN IP: Radar quét xong phải nghỉ ngơi một chút trước khi chuyển trạm
            await asyncio.sleep(random.uniform(0.1, 0.3))
    async def consumer_api_2(self, worker_id, queue, http_client, all_results):
        while True:
            # Lấy mục tiêu từ Hộp thư (Nếu hộp thư trống, lính sẽ tự động đứng chờ)
            task = await queue.get()
            
            route_id = task["route_id"]
            var_id = task["variation_id"]
            stop_id = task["stop_id"]
            
            try:
                url_api_2 = f"https://apicms.ebms.vn/prediction/{route_id}/{var_id}/{stop_id}/predictnextstops/5"
                response = await http_client.get(url_api_2)
                
                if response.status_code == 200:
                    data = response.json()
                    if not data or not data[0].get("arrs"):
                        continue
                    if not data[0].get("arrs"):
                        continue
                    if data and isinstance(data, list) and len(data) > 0:
                        try:
                            base_d = data[0]["arrs"][0]["d"]
                            base_t = data[0]["arrs"][0]["t"]
                            base_stop_id = str(data[0].get("s") or "")
                            crawl_time = datetime.datetime.now()

                            for i in range(1, len(data)):
                                if len(data[i].get("arrs", [])) == 0:
                                    continue
                                
                                curent_d = data[i]["arrs"][0]["d"]
                                curent_t = data[i]["arrs"][0]["t"]
                                next_stop_id = str(data[i].get("s") or "")
                                
                                delta_d = curent_d - base_d
                                delta_t = curent_t - base_t
                                
                                if delta_d > 0 and delta_t > 0:
                                    v_ms = delta_d / delta_t
                                    all_results.append({
                                        "from_stop_id": base_stop_id,
                                        "next_stop_id": next_stop_id,
                                        "distance_to_next_stop": curent_d,
                                        "speed_ms": round(v_ms, 2),
                                        "timestamp": crawl_time
                                    })
                                
                                base_d = curent_d
                                base_t = curent_t
                                base_stop_id = next_stop_id
                        except (IndexError, KeyError):
                            pass
                            
            except Exception as e:
                logger.error(f"[Lính Tỉa {worker_id}] Bắn trượt mục tiêu (route_id={route_id}, var_id={var_id}, stop_id={stop_id})")

            finally:
                queue.task_done()
                await asyncio.sleep(random.uniform(0.01, 0.05))  # Giúp giảm tải cho API và tránh bị ban IP
    async def run_campaign(self):
        logger.info(f"BẮT ĐẦU CHIẾN DỊCH QUÉT LÚC: {datetime.datetime.now()}")
        start_time = time.perf_counter()
        
        queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(10)
        all_results = []
        
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
            consumers = [asyncio.create_task(self.consumer_api_2(i, queue, http_client, all_results)) for i in range(10)]
            total_stops = len(stop_ids)
            completed = 0
            next_log_pct = 10.0    
            logger.info(f"Tung {len(stop_ids)} Radar...")
            producer_tasks = [asyncio.create_task(self.producer_api_1(sid, queue, semaphore, http_client)) for sid in stop_ids]
            for task in asyncio.as_completed(producer_tasks):
                await task
                await asyncio.sleep(0.05)
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
                
        if all_results:
            self.collection.insert_many(all_results)
            logger.info(f"Đã đổ {len(all_results)} kết quả vào MongoDB!")
        else:
            logger.info("Không thu hoạch được dữ liệu.")

        end_time = time.perf_counter()
        logger.info(f"Thời gian thực hiện chiến dịch: {end_time - start_time:.2f} giây")
        return
