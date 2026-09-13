from fastapi import APIRouter

from probelens.api.routes import auth

api_router = APIRouter()
api_router.include_router(auth.router)
