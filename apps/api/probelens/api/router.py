from fastapi import APIRouter

from probelens.api.routes import analytics, auth, saved

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(saved.router)
