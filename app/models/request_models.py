from pydantic import BaseModel

class Chat(BaseModel):
    id: int
    type: str
    
class Message(BaseModel):
    message_id: int
    chat: Chat
    text: str

class TelegramUpdate(BaseModel):
    update_id: int
    message: Message