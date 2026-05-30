from concurrent.futures import ThreadPoolExecutor
import httpx
import asyncio
import json
import pathlib
import math
from tqdm import tqdm
import os

def squared_distance(lat1, lng1, lat2, lng2):
    """
    Hack tốc độ O(1): Tính bình phương khoảng cách.
    Không dùng math.sqrt() để CPU chạy vòng lặp ở tốc độ tối đa.
    """
    return (lat1 - lat2)**2 + (lng1 - lng2)**2

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Tính khoảng cách vật lý thực tế (mét) dựa trên độ cong Trái Đất.
    Chỉ gọi hàm này khi đã cắt xong lát mảng để lấy con số chính xác.
    """
    R = 6371000  # Bán kính Trái Đất (mét)
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def process_route_geometry(stops, polyline_data):
    """
    stops: List các dictionary chứa {"StopId": "...", "Lat": ..., "Lng": ...}
    polyline_data: Dictionary {"Lat": [...], "Lng": [...]}
    """
    
    # ---------------------------------------------------------
    # BƯỚC 1: "Khóa kéo" và Thuật toán Tìm kiếm Tịnh tiến
    # ---------------------------------------------------------
    # Gộp 2 mảng Lat, Lng thành một danh sách các Tuple: [(lat1, lng1), (lat2, lng2)...]
    poly_points = list(zip(polyline_data["lat"], polyline_data["lng"]))
    
    stop_indices = []
    current_poly_idx = 0 # Con trỏ chốt chặn (Bookmark Pointer)
    
    for stop in stops:
        s_lat, s_lng = stop["Lat"], stop["Lng"]
        
        min_sq_dist = float('inf')
        best_idx = current_poly_idx
        
        # Chỉ quét từ vị trí của trạm trước đó trở đi
        for i in range(current_poly_idx, len(poly_points)):
            p_lat, p_lng = poly_points[i]
            sq_dist = squared_distance(s_lat, s_lng, p_lat, p_lng)
            
            if sq_dist < min_sq_dist:
                min_sq_dist = sq_dist
                best_idx = i
        
        stop_indices.append({
            "StopId": stop["StopId"],
            "PolyIndex": best_idx
        })
        
        # Cập nhật con trỏ: Trạm tiếp theo sẽ bắt đầu tìm từ vị trí của trạm này
        current_poly_idx = best_idx

    # ---------------------------------------------------------
    # BƯỚC 2: Cắt lát mảng và Tính tổng khoảng cách
    # ---------------------------------------------------------
    segment_lengths = {}
    
    for i in range(len(stop_indices) - 1):
        stop_1 = stop_indices[i]
        stop_2 = stop_indices[i + 1]
        
        start_idx = stop_1["PolyIndex"]
        end_idx = stop_2["PolyIndex"]
        
        # Ép kiểu an toàn để tránh trường hợp trạm 2 bị giật lùi về sau trạm 1 do nhiễu
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
            
        # Cắt lát mảng (Array Slicing)
        raw_slice = poly_points[start_idx : end_idx + 1]
        segment_slice = []
        for pt in raw_slice:
            # Chỉ thêm điểm vào mảng nếu nó khác với điểm vừa được thêm trước đó
            if not segment_slice or pt != segment_slice[-1]:
                segment_slice.append(pt)
        
        # Tính tổng chiều dài từng khúc nối trong lát cắt
        total_length_m = 0.0
        if len(segment_slice) > 1:
            for j in range(len(segment_slice) - 1):
                p1_lat, p1_lng = segment_slice[j]
                p2_lat, p2_lng = segment_slice[j + 1]
                total_length_m += haversine_distance(p1_lat, p1_lng, p2_lat, p2_lng)
                
        key = f"{stop_1['StopId']}_{stop_2['StopId']}"
        segment_lengths[key] = {
            "length_m": round(total_length_m, 2),
            "path_coords": segment_slice # Giữ lại mảng này để dùng cho Bước 3 (Map Matching OSMnx)
        }
        
    return segment_lengths
    

async def build_segment_lengths():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://buyttphcm.com.vn/" 
    }
    
    src_dir = pathlib.Path(__file__).parent.parent
    stops_file = src_dir / "data" / "master_stops.json"
    output_file = src_dir / "data" / "segment_lengths.json"
    
    with open(stops_file, "r", encoding="utf-8") as f:
        master_stops = json.load(f)
        master_stops_dict = {str(s["StopId"]): s for s in master_stops}
    
    # Use one extra CPU core for pathfinding, but keep it bounded.
    max_workers = min(os.cpu_count() or 4, 4)
    executor = ThreadPoolExecutor(max_workers=max_workers)
    tqdm.write(f"Dùng {max_workers} CPU cores cho pathfinding")
    
    http_timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
    http_limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    http_semaphore = asyncio.Semaphore(8)
    
    async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits) as client:
        tasks = []
        try:
            async with http_semaphore:
                route_res = await client.get("https://apicms.ebms.vn/businfo/getallroute", headers=headers)
            route_data = route_res.json()
        except Exception as e:
            tqdm.write(f"Lỗi khi lấy routes: {e}")
            route_data = []

        # Normalize route list
        if isinstance(route_data, dict):
            routes_list = list(route_data.values())
        elif isinstance(route_data, list):
            routes_list = route_data
        else:
            routes_list = []

        # Prepare progress bars
        routes_bar = tqdm(routes_list, desc="Routes → vars", unit="route")
        vars_bar = tqdm(total=0, desc="Vars → tasks", unit="var")
        paths_bar = tqdm(total=0, desc="Vars → paths", unit="var")
        segments_bar = tqdm(total=0, desc="Paths → segment", unit="var")

        async def process_var(route_id, var):
            # Extract var_id robustly
            var_id = var.get("RouteVarId") if isinstance(var, dict) else var
            try:
                async with http_semaphore:
                    path_res = await client.get(f"https://apicms.ebms.vn/businfo/getpathsbyvar/{route_id}/{var_id}", headers=headers)
                    paths_json = path_res.json()
                    
                    stops_res = await client.get(f"https://apicms.ebms.vn/businfo/getstopsbyvar/{route_id}/{var_id}", headers=headers)
                    stops_json = stops_res.json()

                # Mark that we've fetched a path for this var
                paths_bar.update(1)

                route_stops = []
                for s in stops_json:
                    stop_id = str(s.get("StopId"))
                    if stop_id in master_stops_dict:
                        route_stops.append(master_stops_dict[stop_id])
                
                # Run CPU-bound processing in executor
                loop = asyncio.get_event_loop()
                segment_lengths = await loop.run_in_executor(executor, process_route_geometry, route_stops, paths_json)

                # Mark this var as processed into segments
                segments_bar.update(1)
                return segment_lengths
            except Exception as e:
                tqdm.write(f"Lỗi khi xử lý var {var_id} của tuyến {route_id}: {e}")
                return {}

        # Create tasks while updating vars progress
        for route in routes_bar:
            route_id = route.get("RouteId") if isinstance(route, dict) else route
            try:
                async with http_semaphore:
                    vars_res = await client.get(f"https://apicms.ebms.vn/businfo/getvarsbyroute/{route_id}", headers=headers)
                vars_data = vars_res.json()
            except Exception as e:
                tqdm.write(f"Lỗi khi lấy vars cho route {route_id}: {e}")
                continue

            # Determine number of vars and expand totals for bars
            if isinstance(vars_data, dict):
                nvars = len(vars_data.values())
                vars_iter = list(vars_data.values())
            elif isinstance(vars_data, list):
                nvars = len(vars_data)
                vars_iter = vars_data
            else:
                nvars = 0
                vars_iter = []

            vars_bar.total += nvars
            paths_bar.total += nvars
            segments_bar.total += nvars
            vars_bar.refresh(); paths_bar.refresh(); segments_bar.refresh()

            for var in vars_iter:
                # Increment discovered vars
                vars_bar.update(1)
                tasks.append(asyncio.create_task(process_var(route_id, var)))

        # Thu thập kết quả và gộp các đoạn (hiển thị tiến độ bằng tqdm)
        results = []
        if tasks:
            for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing vars"):
                try:
                    res = await fut
                except Exception as e:
                    tqdm.write(f"Lỗi khi thu thập kết quả task: {e}")
                    continue
                if res:
                    results.append(res)

        # Gộp dictionary trả về từ các tác vụ
        all_segment_lengths = {}
        for r in results:
            for k, v in r.items():
                if k not in all_segment_lengths:
                    all_segment_lengths[k] = v
                else:
                    # Nếu key trùng — giữ giá trị hiện tại (hoặc có thể cập nhật theo chính sách khác)
                    pass

        # Ghi ra file JSON đầu ra
        try:
            with open(output_file, "w", encoding="utf-8") as out_f:
                json.dump(all_segment_lengths, out_f, ensure_ascii=False, indent=2)
            tqdm.write(f"Đã ghi {len(all_segment_lengths)} segment(s) vào {output_file}")
        except Exception as e:
            tqdm.write(f"Lỗi khi ghi file đầu ra: {e}")

        # Đảm bảo đóng executor
        try:
            executor.shutdown(wait=True)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(build_segment_lengths())
        
        
    