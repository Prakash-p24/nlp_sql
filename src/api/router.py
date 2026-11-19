from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.permissions import router as permissions_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(permissions_router)
