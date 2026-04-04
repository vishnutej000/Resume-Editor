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
    selected_projects: list[str] = Field(default_factory=list)
    selected_experience: list[str] = Field(default_factory=list)
    custom_skills: dict[str, str] = Field(default_factory=dict)

    @field_validator('job_role', 'company', 'job_description', mode='before')
    @classmethod
    def sanitize(cls, v):
        return _clean(str(v)) if v else v

    @field_validator('selected_projects', 'selected_experience', mode='before')
    @classmethod
    def sanitize_list(cls, v):
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return [_clean(str(item)) for item in v if _clean(str(item))]
        return []

    @field_validator('custom_skills', mode='before')
    @classmethod
    def sanitize_skills_map(cls, v):
        if not isinstance(v, dict):
            return {}
        cleaned: dict[str, str] = {}
        for k, val in v.items():
            key = _clean(str(k))
            value = _clean(str(val))
            if key and value:
                cleaned[key] = value
        return cleaned


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


class ApplyResumeEditsRequest(BaseModel):
    app_id: Optional[str] = None
    base_latex: str = Field(..., min_length=10, max_length=500_000)
    tailored_summary: Optional[str] = None
    tailored_skills: dict[str, str] = Field(default_factory=dict)
    tailored_projects: list[dict] = Field(default_factory=list)
    tailored_experience: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator('app_id', 'base_latex', 'tailored_summary', mode='before')
    @classmethod
    def sanitize_text(cls, v):
        return _clean(str(v)) if v is not None else v

    @field_validator('tailored_skills', mode='before')
    @classmethod
    def sanitize_skills(cls, v):
        if not isinstance(v, dict):
            return {}
        cleaned: dict[str, str] = {}
        for k, val in v.items():
            key = _clean(str(k))
            value = _clean(str(val))
            if key:
                cleaned[key] = value
        return cleaned

    @field_validator('tailored_projects', mode='before')
    @classmethod
    def sanitize_projects(cls, v):
        if not isinstance(v, list):
            return []
        projects: list[dict] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            name = _clean(str(item.get('name', '')))
            tech = _clean(str(item.get('tech_stack', '')))
            raw_bullets = item.get('bullets', [])
            bullets = [_clean(str(b)) for b in raw_bullets if _clean(str(b))] if isinstance(raw_bullets, list) else []
            if name:
                projects.append({"name": name, "tech_stack": tech, "bullets": bullets})
        return projects

    @field_validator('tailored_experience', mode='before')
    @classmethod
    def sanitize_experience(cls, v):
        if not isinstance(v, dict):
            return {}
        experience: dict[str, list[str]] = {}
        for company, bullets in v.items():
            comp = _clean(str(company))
            if not comp:
                continue
            if isinstance(bullets, list):
                cleaned_bullets = [_clean(str(b)) for b in bullets if _clean(str(b))]
            else:
                cleaned_bullets = []
            experience[comp] = cleaned_bullets
        return experience


class RenderPdfRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    folder_name: Optional[str] = None
    latex: str = Field(..., min_length=10, max_length=500_000)

    @field_validator('app_id', 'folder_name', 'latex', mode='before')
    @classmethod
    def sanitize_text(cls, v):
        return _clean(str(v)) if v is not None else v
