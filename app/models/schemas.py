from pydantic import BaseModel
from typing import Literal
from pydantic import Field
    
class Location(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Vĩ độ, giá trị từ -90 đến 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Kinh độ, giá trị từ -180 đến 180")

class RoutingRequest(BaseModel):
    user_id: str = Field(..., alias="userId", description="ID người dùng")
    conversation_id: str = Field(..., alias="conversationId")
    platform: Literal["telegram", "java_app"] = Field(..., description="Nền tảng gửi yêu cầu")
    callback_url: str | None = Field(None, alias="callbackUrl")
    origin: Location
    destination: Location
    
    class Config:
        validate_by_name = True

class RoutingResponse(BaseModel):
    user_id: str = Field(..., alias="userId", description="ID người dùng")
    conversation_id: str = Field(..., alias="conversationId")
    status: Literal["success", "error", "pending"]
    message: str
    distance_km: float | None = None   
    estimated_time_min: float | None = None
    geojson: dict | None = Field(None, description="Dữ liệu GeoJSON của lộ trình")
    navigation_url: str | None = Field(None, description="URL Google Maps")
    route_id: str | None = None
    metadata: dict | None = Field(default_factory=dict, description="Thông tin bổ sung về lộ trình")