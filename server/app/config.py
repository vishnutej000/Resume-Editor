from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Complex model: DeepSeek V3 via NVIDIA NIM ──────────────────────────
    # Used for: JD analysis + full resume tailoring (project/experience selection + bullets)
    COMPLEX_MODEL: str = "nvidia_nim/deepseek-ai/deepseek-v3-0324"
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    # ── Simple model: Groq Llama ────────────────────────────────────────────
    # Used for: lightweight/fast tasks and as secondary fallback
    SIMPLE_MODEL: str = "groq/llama-3.3-70b-versatile"
    GROQ_API_KEY: str = ""

    # ── Fallback: triggered when complex model fails ────────────────────────
    FALLBACK_MODEL: str = "cerebras/llama3.1-8b"
    FALLBACK_API_KEY: str = ""

    # ── AI generation globals (temperature=0.0 everywhere = no hallucination) ──
    AI_TIMEOUT: int = 120
    MAX_TOKENS: int = 4096
    COMPLEX_TEMPERATURE: float = 0.0
    SIMPLE_TEMPERATURE: float = 0.0

    # ── Project / experience pre-ranking ───────────────────────────────────
    # LLM sees (required_slots * PROJECT_CANDIDATE_MULTIPLIER) top-ranked entries
    PROJECT_CANDIDATE_MULTIPLIER: int = 2
    ATS_MATCH_THRESHOLD: float = 0.6

    # ── File paths ──────────────────────────────────────────────────────────
    BASE_RESUME_PATH: str = "../base/resume.tex"
    PROJECTS_BANK_PATH: str = "../base/projects.tex"
    EXPERIENCE_BANK_PATH: str = "../base/experience.tex"

    OUTPUTS_DIR: str = "outputs"
    DATA_DIR: str = "data"

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Set to true to enable LanceDB semantic search (downloads ~67MB ONNX model on first run)
    SEMANTIC_SEARCH: bool = False

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
