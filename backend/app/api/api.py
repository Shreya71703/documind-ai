from fastapi import APIRouter
from app.api.endpoints import auth
from app.api.endpoints import documents
from app.api.endpoints import retrieval
from app.api.endpoints import chats

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(retrieval.router, prefix="/retrieval", tags=["Retrieval"])
api_router.include_router(chats.router, prefix="/chats", tags=["Chats"])
