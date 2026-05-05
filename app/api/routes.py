from fastapi import APIRouter
from rich import text
from app.models import request_models

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
        print(f"Received message from chat {chat_id}: {text}")
    else:
        print(f"Received message from chat {chat_id} with no text")
    return {"status": "received", "update_id": update.update_id}