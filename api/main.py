from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.router import api_router
from api.services.workspace import setup_workspace


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_workspace()
    yield


app = FastAPI(title="GraphGen API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
