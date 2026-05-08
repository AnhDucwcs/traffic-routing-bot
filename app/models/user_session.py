import time
from pydantic import BaseModel

class UserSession(BaseModel):
    state: str  # "awaiting_start" hoặc "awaiting_end"
    start_lat: float | None = None
    start_lng: float | None = None
    last_updated: float = 0.0 # Lưu thời gian dạng time.time() để xử lý TTL