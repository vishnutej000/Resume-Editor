from fastapi import APIRouter
from app.models.response import HealthResponse
from app.config import settings

router = APIRouter()


def _mask(key: str) -> str:
    if not key or len(key) < 8:
        return "NOT SET"
    return key[:6] + "..." + key[-4:]


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        model=settings.MODEL,
        provider=settings.PROVIDER,
    )


@router.get("/debug/config")
async def debug_config():
    return {
        "model": settings.MODEL,
        "provider": settings.PROVIDER,
        "api_key_loaded": _mask(settings.API_KEY),
        "api_key_has_quotes": settings.API_KEY.startswith('"') or settings.API_KEY.startswith("'"),
        "fallback_model": settings.FALLBACK_MODEL or "not set",
        "fallback_key_loaded": _mask(settings.FALLBACK_API_KEY),
        "base_resume_path": settings.BASE_RESUME_PATH,
        "projects_bank_path": settings.PROJECTS_BANK_PATH,
        "experience_bank_path": settings.EXPERIENCE_BANK_PATH,
    }
