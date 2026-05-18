from fastapi import APIRouter
from fastapi import Request
from app.models.schemas import RoutingRequest
from app.models.user_session import UserSession
from app.services.core_logic import process_routing_request


router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Welcome to the Traffic Routing Bot API!"}

@router.get("/health-check")
@router.head("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/api/v1/routing")
async def core_routing_api(payload: RoutingRequest, request: Request):
    result = await process_routing_request(payload, request.app.state)
    if result["status"] == "success":
        return {
            "message": result["message"],
            "url": result["url"]
        }
    else: 
        return {"message": result["message"]}