from fastapi import APIRouter, Request, BackgroundTasks
from app.models import request_models


router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Welcome to the Traffic Routing Bot API!"}

@router.get("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/webhook/telegram")
async def telegram_webhook(update: request_models.TelegramUpdate, request: Request, background_tasks: BackgroundTasks):
    user_sessions = request.app.state.user_sessions
    graph = request.app.state.graph
    # Use bot instance attached to app.state (created in lifespan)
    background_tasks.add_task(request.app.state.bot.process_update, update, user_sessions, graph)
    return {"status": "OK"}
