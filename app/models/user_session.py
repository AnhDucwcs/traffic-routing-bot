from pydantic import BaseModel

class UserSession(BaseModel):
    chat_id: int
    state: str  # "awaiting_start" hoặc "awaiting_end"
    start_lat: float | None = None
    start_lng: float | None = None