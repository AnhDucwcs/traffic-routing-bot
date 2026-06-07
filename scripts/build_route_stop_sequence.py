import httpx
import asyncio
import json
import pathlib
from tqdm import tqdm
import os

async def build_route_stop_sequence():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://buyttphcm.com.vn/" 
    }
    src_dir = pathlib.Path(__file__).parent.parent
    stops_file = src_dir / "data" / "master_stops.json"
    output_file = src_dir / "data" / "route_stop_sequence.json"
    
    with open(stops_file, "r", encoding="utf-8") as f:
        master_stops = json.load(f)
        master_stops_dict = {str(s["StopId"]): s for s in master_stops}
    
    http_timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
    http_limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    http_semaphore = asyncio.Semaphore(8)
    
    sequence_results = {}
    
    async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits) as client:
        tasks = []
        try:
            async with http_semaphore:
                route_res = await client.get("https://apicms.ebms.vn/businfo/getallroute", headers=headers)
            route_res.raise_for_status()
            try:
                route_data = route_res.json()
            except ValueError:
                tqdm.write("Lỗi: response JSON không hợp lệ khi lấy routes")
                route_data = []
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

        # Prepare progress bars (use fixed positions to avoid overlap)
        routes_bar = tqdm(routes_list, desc="Routes → vars", unit="route", position=0)
        vars_bar = tqdm(total=0, desc="Vars → tasks", unit="var", position=1)
        paths_bar = tqdm(total=0, desc="Vars → stops", unit="var", position=2)
        sequence_bar = tqdm(total=0, desc="Stops → sequence", unit="var", position=3)

        async def process_var(route_id, var):
            var_id = var.get("RouteVarId") if isinstance(var, dict) else var
            try:
                async with http_semaphore:
                    stops_res = await client.get(f"https://apicms.ebms.vn/businfo/getstopsbyvar/{route_id}/{var_id}", headers=headers)
                stops_res.raise_for_status()
                try:
                    stops_json = stops_res.json()
                except ValueError:
                    tqdm.write(f"Lỗi: response JSON không hợp lệ cho var {var_id} của route {route_id}")
                    return {}

                route_stops = []
                paths_bar.update(1)
                for s in stops_json:
                    stop_id = s.get("StopId")
                    if stop_id is None:
                        continue
                    stop_id_str = str(stop_id)
                    if stop_id_str in master_stops_dict:
                        route_stops.append(master_stops_dict[stop_id_str])

                # Nếu không có stops phù hợp thì bỏ qua
                if not route_stops:
                    return {}

                first_stop_id = route_stops[0].get("StopId")
                key = f"{route_id}_{var_id}_{first_stop_id}"
                sequence_results[key] = ""
                for i in range(1, len(route_stops)):
                    cur = route_stops[i].get("StopId")
                    prev = route_stops[i-1].get("StopId")
                    key = f"{route_id}_{var_id}_{cur}"
                    sequence_results[key] = f"{prev}"

                sequence_bar.update(1)
                return {}

            except Exception as e:
                tqdm.write(f"Lỗi khi xử lý var {var_id} của tuyến {route_id}: {e}")
                return {}
        
        for route in routes_bar:
            route_id = route.get("RouteId") if isinstance(route, dict) else route
            try:
                async with http_semaphore:
                    vars_res = await client.get(f"https://apicms.ebms.vn/businfo/getvarsbyroute/{route_id}", headers=headers)
                vars_res.raise_for_status()
                try:
                    vars_data = vars_res.json()
                except ValueError:
                    tqdm.write(f"Lỗi: response JSON không hợp lệ khi lấy vars cho route {route_id}")
                    continue
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
            sequence_bar.total += nvars
            vars_bar.refresh(); paths_bar.refresh(); sequence_bar.refresh()

            for var in vars_iter:
                # Increment discovered vars
                vars_bar.update(1)
                tasks.append(asyncio.create_task(process_var(route_id, var)))
        
        if tasks:
            # Wrap the as_completed iterator with tqdm at its own position
            for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing vars", position=4):
                try:
                    res = await fut
                except Exception as e:
                    tqdm.write(f"Lỗi khi thu thập kết quả task: {e}")
                    continue
            
        try:
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as out_f:
                json.dump(sequence_results, out_f, ensure_ascii=False, indent=2)
            tqdm.write(f"Đã ghi {len(sequence_results)} sequence(s) vào {output_file}")
        except Exception as e:
            tqdm.write(f"Lỗi khi ghi file đầu ra: {e}")


if __name__ == "__main__": 
    asyncio.run(build_route_stop_sequence())