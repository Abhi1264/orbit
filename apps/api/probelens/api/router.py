from fastapi import APIRouter

from probelens.api.routes import analytics, anomalies, auth, comments, investigations, saved

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(saved.router)
api_router.include_router(anomalies.router)
api_router.include_router(investigations.router)
api_router.include_router(comments.router)
