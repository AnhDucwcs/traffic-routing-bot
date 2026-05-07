import fastapi
from contextlib import asynccontextmanager
from app.api.routes import router
from app.core.config import settings
from app.services.routing.map_builder import load_routing_graph

async def lifespan(app: fastapi.FastAPI):
    app.state.graph = load_routing_graph()
    
    yield
    
    print("Shutting down application...")
    del app.state.graph

app = fastapi.FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.include_router(router)