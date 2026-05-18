from fastapi import APIRouter


router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Welcome to the Traffic Routing Bot API!"}

@router.get("/health-check")
@router.head("/health-check")
async def health_check():
    return {"status": "healthy"}

