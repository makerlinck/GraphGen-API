from fastapi import APIRouter

from api.routes import connection, health, jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(connection.router)
api_router.include_router(jobs.router)
