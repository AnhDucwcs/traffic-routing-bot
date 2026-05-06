from fastapi import APIRouter
from rich import text
from app.models import request_models
from app.services.telegram_bot import bot
from app.services.crawler.bus_crawler import crawler

router = APIRouter()

@router.get("/health-check")
async def health_check():
    return {"status": "healthy"}

@router.post("/webhook")
async def handle_webhook(update: request_models.TelegramUpdate):
    if update.message:
        chat_id = update.message.chat.id
        text = update.message.text
    elif update.edited_message:
        chat_id = update.edited_message.chat.id
        text = update.edited_message.text
    else:
        print("Update does not support")
        return {"status": "unsupported update type", "update_id": update.update_id}
    if text:
        await bot.send_message(chat_id, f"Received your message: {text}")
    else:
        await bot.send_message(chat_id, "Received your message, but it has no text.")
    return {"status": "received", "update_id": update.update_id}

@router.get("/crawl")
async def crawl():
    route_id = "66"
    direction = 1
    stop_id = "26"
    limit = 5
    results = await crawler.get_next_stops_prediction(route_id, direction, stop_id, limit)
    return {"results": results}