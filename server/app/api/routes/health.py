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
        complex_model=settings.COMPLEX_MODEL,
        simple_model=settings.SIMPLE_MODEL,
    )


@router.get("/debug/config")
async def debug_config():
    return {
        "complex_model": settings.COMPLEX_MODEL,
        "simple_model": settings.SIMPLE_MODEL,
        "fallback_model": settings.FALLBACK_MODEL or "not set",
        "nvidia_api_key": _mask(settings.NVIDIA_API_KEY),
        "groq_api_key": _mask(settings.GROQ_API_KEY),
        "fallback_api_key": _mask(settings.FALLBACK_API_KEY),
        "ai_timeout": settings.AI_TIMEOUT,
        "max_tokens": settings.MAX_TOKENS,
        "complex_temperature": settings.COMPLEX_TEMPERATURE,
        "project_candidate_multiplier": settings.PROJECT_CANDIDATE_MULTIPLIER,
        "ats_match_threshold": settings.ATS_MATCH_THRESHOLD,
        "base_resume_path": settings.BASE_RESUME_PATH,
        "projects_bank_path": settings.PROJECTS_BANK_PATH,
        "experience_bank_path": settings.EXPERIENCE_BANK_PATH,
    }
