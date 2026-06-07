import httpx
import asyncio
import json
import pathlib

async def fetch_all_stops():
    url = "https://apicms.ebms.vn/businfo/getstopsinbounds/106.58/10.70/106.82/10.88"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://buyttphcm.com.vn/" 
    }
    
    src_dir = pathlib.Path(__file__).parent.parent
    output_file = src_dir / "data/master_stops.json"
    

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Đang gửi yêu cầu lấy toàn bộ trạm xe buýt...")
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            stops = response.json()
            results = []
            
            for stop in stops:
                result = {
                    "StopId": stop.get("StopId"),
                    "Name": stop.get("Name"),
                    "Lat": stop.get("Lat"),
                    "Lng": stop.get("Lng"),
                    "Routes": [r.strip() for r in stop.get("Routes", "").split(',')]
                }
                results.append(result)
            
            print(f"Thành công! Đã gom được {len(stops)} trạm dừng.")
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
                
            print(f"Đã lưu an toàn vào file '{output_file}'")
            
            # In thử 1 trạm đầu tiên để xem cấu trúc
            if stops:
                print("\nCấu trúc dữ liệu của 1 trạm:")
                print(results[0])
                
        except Exception as e:
            print(f"Có lỗi xảy ra: {e}")

if __name__ == "__main__":
    asyncio.run(fetch_all_stops())