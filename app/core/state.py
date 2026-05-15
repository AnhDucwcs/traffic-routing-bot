from cachetools import TTLCache
import asyncio
from collections import defaultdict


class SessionStore:
    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        self.store = TTLCache(maxsize=maxsize, ttl=ttl)
        # defaultdict that creates asyncio.Lock objects per chat id
        self.locks = defaultdict(asyncio.Lock)

    def get_store(self):
        return self.store

    def get_lock(self, chat_id):
        return self.locks[chat_id]


def init_app_state(app, maxsize: int = 10000, ttl: int = 300):
    """Initialize session store on the given FastAPI app state."""
    store = SessionStore(maxsize=maxsize, ttl=ttl)
    app.state.user_sessions = store.store
    app.state.user_session_locks = store.locks


def shutdown_app_state(app):
    try:
        app.state.user_sessions.clear()
    except Exception:
        pass
    try:
        app.state.user_session_locks.clear()
    except Exception:
        pass
