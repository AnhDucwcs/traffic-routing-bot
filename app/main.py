import fastapi
from app.api.routes import router
from app.core.config import settings

app = fastapi.FastAPI(title=settings.PROJECT_NAME)
app.include_router(router)