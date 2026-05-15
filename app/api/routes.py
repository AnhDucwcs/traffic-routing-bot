from fastapi import APIRouter, Request, BackgroundTasks
from app.models import request_models
from app.services.telegram_bot import bot


router = APIRouter()

@router.get("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/webhook/telegram")
async def telegram_webhook(update: request_models.TelegramUpdate, request: Request, background_tasks: BackgroundTasks):
    user_sessions = request.app.state.user_sessions
    graph = request.app.state.graph
    background_tasks.add_task(bot.process_update, update, user_sessions, graph)
    return {"status": "OK"}
