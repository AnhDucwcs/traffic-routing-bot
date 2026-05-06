import httpx
from app.core.config import settings

class BusCrawler:
    def __init__(self):
        self.session = httpx.AsyncClient(timeout=10.0) 
        self.base_url = settings.BUS_API_BASE_URL

    async def get_next_stops_prediction(self, route_id: str, direction: int, stop_id: str, limit: int = 3):
        url = f"{self.base_url}/prediction/{route_id}/{direction}/{stop_id}/predictnextstops/{limit}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()
        except httpx.HTTPError as e:
            print(f"Lỗi khi gọi API xe buýt: {e}")
            return None
        
        if not data:
            return None
        
        results = []
        
        try:
            base_d = data[0]["arrs"][0]["d"]
            base_t = data[0]["arrs"][0]["t"]
        except IndexError:
            print("There are no upcoming buses for base stop. Skipping!")
            return None
        
        for i in range(1, len(data)):
            if len(data[i]["arrs"]) == 0:
                print(f"There are no upcoming buses for stop {i}. Skipping!")
                continue
            
            curent_d = data[i]["arrs"][0]["d"]
            curent_t = data[i]["arrs"][0]["t"]
            
            detal_d = curent_d - base_d
            detal_t = curent_t - base_t
            
            if detal_d <= 0 or detal_t <= 0:
                print(f"Invalid data for stop {i}. Skipping!")
                continue
            
            v_ms = detal_d / detal_t
            results.append({"stop": data[i]["sN"], "speed_ms": v_ms})

            base_d = curent_d
            base_t = curent_t
        
        return results

crawler = BusCrawler()
            