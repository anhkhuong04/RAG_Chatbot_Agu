"""
API v1 endpoints package
"""
from fastapi import APIRouter
from app.api.v1.endpoints import admin, chat

api_router = APIRouter()

# Include admin routes
api_router.include_router(admin.router)

# Include chat routes
api_router.include_router(chat.router)
