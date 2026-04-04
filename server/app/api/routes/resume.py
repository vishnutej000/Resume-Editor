import uuid
import logging
import json
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException
import aiofiles
from app.models.request import TailorResumeRequest, AnalyzeJDRequest, ApplyResumeEditsRequest, RenderPdfRequest
from app.models.response import TailorResumeResponse, JDAnalysis
from app.core import jd_analyzer, resume_editor, pdf_generator, storage
from app.db import duckdb_client, lancedb_client
from app.config import settings
from app.utils import latex_utils

logger = logging.getLogger(__name__)

router = APIRouter()


def _pdf_unavailable_warning() -> str:
    engine = pdf_generator.get_available_engine()
    if not engine:
        return "PDF not generated: no LaTeX compiler found in PATH (pdflatex/xelatex/lualatex/tectonic)."
    return f"PDF not generated: {engine} compilation failed. Check generated resume.tex for invalid LaTeX content."


def _normalize_latex_for_compile(latex: str) -> str:
    text = (latex or "").replace("\r\n", "\n").replace("\r", "\n")

    # Optional-argument blocks cannot contain paragraph breaks.
    pattern = re.compile(
        r'(\\(?:usepackage|documentclass)\s*\[)(.*?)(\]\s*(?:\{[^}]+\})?)',
        re.DOTALL,
    )

    def _compact_optional(match: re.Match) -> str:
        inner = re.sub(r'\n\s*\n+', '\n', match.group(2))
        return f"{match.group(1)}{inner}{match.group(3)}"

    text = pattern.sub(_compact_optional, text)

    # Compact paragraph breaks only inside key-value command bodies.
    # Global paragraph collapsing changes visual spacing/alignment of the base template.
    kv_body_patterns = [
        re.compile(r'(\\hypersetup\s*\{)(.*?)(\})', re.DOTALL),
        re.compile(r'(\\setlist(?:\[[^\]]+\])?\s*\{)(.*?)(\})', re.DOTALL),
    ]

    def _compact_kv_body(match: re.Match) -> str:
        inner = re.sub(r'\n\s*\n+', '\n', match.group(2))
        return f"{match.group(1)}{inner}{match.group(3)}"

    for kv_pattern in kv_body_patterns:
        text = kv_pattern.sub(_compact_kv_body, text)

    return text


@router.get("/resume-options")
async def resume_options():
    """Return selectable project/experience options and editable base skills."""
    try:
        latex_resume = storage.load_base_resume()
        projects_bank = storage.load_projects_bank()
        experience_bank = storage.load_experience_bank()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Base file not found: {e}. Check BASE_RESUME_PATH, PROJECTS_BANK_PATH, EXPERIENCE_BANK_PATH in .env")

    current_projects = latex_utils.extract_projects(latex_resume)
    bank_projects = latex_utils.extract_projects(projects_bank)
    current_experience = latex_utils.extract_experience(latex_resume)
    bank_experience = latex_utils.extract_experience(experience_bank)
    base_skills = latex_utils.extract_skills(latex_resume)

    experience_options = [
        {
            "company": company,
            "bullets": bullets,
            "selectable": True,
        }
        for company, bullets in bank_experience.items()
    ]

    if not experience_options:
        experience_options = [
            {
                "company": company,
                "bullets": bullets,
                "selectable": True,
            }
            for company, bullets in current_experience.items()
        ]

    return {
        "projects": [
            {
                "name": p.get("name", ""),
                "full_name": p.get("full_name", p.get("name", "")),
                "tech_stack": p.get("tech_stack", ""),
                "bullets": p.get("bullets", []),
            }
            for p in (bank_projects or current_projects)
        ],
        "experience": experience_options,
        "selectable_experience_companies": list(current_experience.keys()),
        "base_skills": base_skills,
        "default_selected_projects": [p.get("name", "") for p in current_projects],
        "default_selected_experience": list(current_experience.keys()),
    }


@router.post("/analyze-jd")
async def analyze_jd(req: AnalyzeJDRequest):
    try:
        result = await jd_analyzer.analyze(req.job_role, req.job_description)
        result["jd_quality"] = jd_analyzer.assess_jd_quality(
            job_role=req.job_role,
            job_description=req.job_description,
            analysis=result,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-edits")
async def apply_edits(req: ApplyResumeEditsRequest):
    try:
        result = resume_editor.apply_manual_edits(
            latex_resume=req.base_latex,
            tailored_summary=req.tailored_summary,
            tailored_skills=req.tailored_skills,
            tailored_projects=req.tailored_projects,
            tailored_experience=req.tailored_experience,
        )

        pdf_available: bool | None = None
        folder_name = None

        if req.app_id:
            record = duckdb_client.get_application(req.app_id)
            if not record:
                raise HTTPException(status_code=404, detail="Application not found")

            folder_name = record["folder_name"]
            output_path = storage.get_output_path(folder_name)
            tex_path = output_path / "resume.tex"
            normalized_latex = _normalize_latex_for_compile(result.get("updated_latex", req.base_latex))

            async with aiofiles.open(tex_path, "w", encoding="utf-8") as f:
                await f.write(normalized_latex)

            result["updated_latex"] = normalized_latex

            structured_data = {
                "tailored_summary": result.get("tailored_summary", ""),
                "tailored_skills": result.get("tailored_skills", {}),
                "tailored_projects": result.get("tailored_projects", []),
                "tailored_experience": result.get("tailored_experience", {}),
            }
            async with aiofiles.open(output_path / "structured_data.json", "w", encoding="utf-8") as f:
                await f.write(json.dumps(structured_data, indent=2))

            pdf_path = await pdf_generator.generate(tex_path, output_path)
            pdf_available = pdf_path is not None
            duckdb_client.update_pdf_status(req.app_id, pdf_available)

            if not pdf_available:
                result.setdefault("warnings", []).append(_pdf_unavailable_warning())

        result["pdf_available"] = pdf_available
        result["id"] = req.app_id
        result["folder_name"] = folder_name
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("apply_edits failed")
        detail = str(e).strip() or f"{type(e).__name__} in apply_edits"
        raise HTTPException(status_code=500, detail=detail)


@router.post("/render-pdf")
async def render_pdf(req: RenderPdfRequest):
    try:
        folder_name = req.folder_name if req.folder_name and storage.folder_exists(req.folder_name) else None
        if not folder_name:
            record = duckdb_client.get_application(req.app_id)
            if not record:
                raise HTTPException(status_code=404, detail="Application not found")
            folder_name = record["folder_name"]

        output_path = storage.get_output_path(folder_name)
        tex_path = output_path / "resume.tex"
        normalized_latex = _normalize_latex_for_compile(req.latex)

        async with aiofiles.open(tex_path, "w", encoding="utf-8") as f:
            await f.write(normalized_latex)

        pdf_path = await pdf_generator.generate(tex_path, output_path)
        has_pdf = pdf_path is not None
        try:
            duckdb_client.update_pdf_status(req.app_id, has_pdf)
        except Exception as e:
            logger.warning("Unable to update PDF status for %s: %s", req.app_id, e)

        warnings: list[str] = []
        if not has_pdf:
            warnings.append(_pdf_unavailable_warning())

        return {
            "id": req.app_id,
            "folder_name": folder_name,
            "pdf_available": has_pdf,
            "updated_latex": normalized_latex,
            "warnings": warnings,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("render_pdf failed")
        detail = str(e).strip() or f"{type(e).__name__} in render_pdf"
        raise HTTPException(status_code=500, detail=detail)


@router.post("/tailor-resume", response_model=TailorResumeResponse)
async def tailor_resume(req: TailorResumeRequest):
    try:
        latex_resume = storage.load_base_resume()
        projects_bank = storage.load_projects_bank()
        experience_bank = storage.load_experience_bank()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Base file not found: {e}. Check BASE_RESUME_PATH, PROJECTS_BANK_PATH, EXPERIENCE_BANK_PATH in .env")

    try:
        jd_analysis = await jd_analyzer.analyze(req.job_role, req.job_description)
        jd_quality = jd_analyzer.assess_jd_quality(
            job_role=req.job_role,
            job_description=req.job_description,
            analysis=jd_analysis,
            company=req.company,
        )

        if not jd_quality.get("is_valid", False):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Job description does not clearly define role intent and requirements.",
                    "checks": jd_quality.get("checks", {}),
                    "warnings": jd_quality.get("warnings", []),
                },
            )

        result = await resume_editor.tailor(
            latex_resume=latex_resume,
            projects_bank=projects_bank,
            experience_bank=experience_bank,
            jd_analysis=jd_analysis,
            target_domain=req.target_domain,
            selected_project_names=req.selected_projects,
            selected_experience_companies=req.selected_experience,
            custom_skills=req.custom_skills,
        )

        if jd_quality.get("warnings"):
            result.setdefault("warnings", []).extend(jd_quality["warnings"])
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("tailor_resume failed")
        detail = str(e).strip() or f"{type(e).__name__} in tailor_resume"
        raise HTTPException(status_code=500, detail=detail)

    app_id = str(uuid.uuid4())
    folder_name = storage.make_folder_name(req.company, req.job_role)
    created_at = datetime.utcnow()

    await storage.save_run(
        folder_name=folder_name,
        latex=result["updated_latex"],
        jd_text=req.job_description,
        analysis=jd_analysis,
        changes={
            "change_rationale": result.get("change_rationale"),
            "keyword_coverage": result.get("keyword_coverage"),
            "warnings": result.get("warnings", []),
        },
        structured_data={
            "tailored_summary": result.get("tailored_summary", ""),
            "tailored_skills": result.get("tailored_skills", {}),
            "tailored_projects": result.get("tailored_projects", []),
            "tailored_experience": result.get("tailored_experience", {}),
        }
    )

    output_path = storage.get_output_path(folder_name)
    tex_path = output_path / "resume.tex"

    normalized_latex = _normalize_latex_for_compile(result.get("updated_latex", ""))
    async with aiofiles.open(tex_path, "w", encoding="utf-8") as f:
        await f.write(normalized_latex)
    result["updated_latex"] = normalized_latex

    pdf_path = await pdf_generator.generate(tex_path, output_path)
    has_pdf = pdf_path is not None

    if not has_pdf:
        result.setdefault("warnings", []).append(_pdf_unavailable_warning())

    duckdb_client.insert_application({
        "id": app_id,
        "company": req.company,
        "role": req.job_role,
        "created_at": created_at,
        "folder_name": folder_name,
        "has_pdf": has_pdf,
        "jd_preview": req.job_description[:400],
        "change_rationale": result.get("change_rationale", ""),
        "keywords_covered": result.get("keyword_coverage", {}).get("covered", []),
        "keywords_missing": result.get("keyword_coverage", {}).get("missing", []),
        "warnings": result.get("warnings", []),
    })

    if settings.SEMANTIC_SEARCH:
        try:
            lancedb_client.add_jd_embedding(
                app_id=app_id,
                company=req.company,
                role=req.job_role,
                jd_text=req.job_description,
                created_at=created_at.isoformat(),
            )
        except Exception as e:
            logger.warning("LanceDB embedding failed for %s: %s", app_id, e)

    return TailorResumeResponse(
        id=app_id,
        company=req.company,
        role=req.job_role,
        jd_analysis=JDAnalysis(**jd_analysis),
        tailored_summary=result.get("tailored_summary", ""),
        tailored_skills=result.get("tailored_skills", {}),
        tailored_projects=result.get("tailored_projects", []),
        tailored_experience=result.get("tailored_experience", {}),
        updated_latex=result.get("updated_latex", ""),
        keyword_coverage=result.get("keyword_coverage", {}),
        ats_score=result.get("ats_score", {"score": 0, "matched": [], "missing": [], "total_keywords": 0}),
        change_rationale=result.get("change_rationale", ""),
        warnings=result.get("warnings", []),
        pdf_available=has_pdf,
        folder_name=folder_name,
        created_at=created_at,
    )
