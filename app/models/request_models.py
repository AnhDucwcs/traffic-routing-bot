from pydantic import BaseModel

class Chat(BaseModel):
    id: int
    type: str
    
class Message(BaseModel):
    message_id: int
    chat: Chat
    text: str | None = None

class TelegramUpdate(BaseModel):
    update_id: int
    message: Message | None = None
    edited_message: Message | None = None
    # Sau này làm nút bấm thì bỏ comment dòng dưới
    # callback_query: CallbackQuery | None = None