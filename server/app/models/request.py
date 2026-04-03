import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional


def _clean(v: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v).strip()


class TailorResumeRequest(BaseModel):
    job_role: str = Field(..., min_length=2)
    company: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=50, max_length=50_000)
    target_domain: Optional[str] = None

    @field_validator('job_role', 'company', 'job_description', mode='before')
    @classmethod
    def sanitize(cls, v):
        return _clean(str(v)) if v else v


class AnalyzeJDRequest(BaseModel):
    job_role: str
    job_description: str = Field(..., min_length=50, max_length=50_000)

    @field_validator('job_role', 'job_description', mode='before')
    @classmethod
    def sanitize(cls, v):
        return _clean(str(v)) if v else v


class SearchHistoryRequest(BaseModel):
    query: str = Field(..., min_length=2)
    limit: int = Field(default=5, ge=1, le=20)
