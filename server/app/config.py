from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    PROVIDER: str = "groq"
    MODEL: str = "groq/llama-3.3-70b-versatile"
    API_KEY: str = ""

    FALLBACK_MODEL: str = ""
    FALLBACK_API_KEY: str = ""

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
