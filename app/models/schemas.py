from pydantic import BaseModel
from typing import Literal

class RoutingRequest(BaseModel):
    user_id: str
    platform: Literal["telegram", "java_web"]  # Có thể mở rộng thêm các nền tảng khác sau này
    latitude: float
    longitude: float

class RoutingResponse(BaseModel):
    status: Literal["success", "error", "pending"]
    message: str
    distance_km: float | None = None   
    estimated_time_min: float | None = None
    geojson: dict | None = None
    navigation_url: str | None = None
    map_image_url: str | None = None
    
class Location(BaseModel):
    lat: float
    lng: float

class JavaRoutingRequest(BaseModel):
    userId: str
    conversationId: str
    platform: str
    callbackUrl: str
    origin: Location
    destination: Location