from pydantic import BaseModel
from typing import Literal

class RoutingRequest(BaseModel):
    user_id: str
    platform: Literal["telegram", "java_web"]  # Có thể mở rộng thêm các nền tảng khác sau này
    latitude: float
    longitude: float