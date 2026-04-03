from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class JDAnalysis(BaseModel):
    target_role: str
    must_have_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    domain: str
    experience_level: str
    ats_keywords: list[str]
    summary: str


class TailorResumeResponse(BaseModel):
    id: str
    company: str
    role: str
    jd_analysis: JDAnalysis
    tailored_summary: str
    tailored_skills: dict[str, str]
    tailored_projects: list[dict]
    tailored_experience: dict[str, list[str]]
    updated_latex: str
    keyword_coverage: dict[str, list[str]]
    change_rationale: str
    warnings: list[str]
    pdf_available: bool
    folder_name: str
    created_at: datetime


class ApplicationRecord(BaseModel):
    id: str
    company: str
    role: str
    created_at: datetime
    folder_name: str
    has_pdf: bool
    jd_preview: str
    warnings_count: int


class HistoryResponse(BaseModel):
    total: int
    applications: list[ApplicationRecord]


class HealthResponse(BaseModel):
    status: str
    model: str
    provider: str
    version: str = "1.0.0"
