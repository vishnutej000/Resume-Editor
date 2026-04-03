import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.models.request import TailorResumeRequest, AnalyzeJDRequest
from app.models.response import TailorResumeResponse, JDAnalysis
from app.core import jd_analyzer, resume_editor, pdf_generator, storage
from app.db import duckdb_client, lancedb_client
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


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
        )

        if jd_quality.get("warnings"):
            result.setdefault("warnings", []).extend(jd_quality["warnings"])
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

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
    pdf_path = await pdf_generator.generate(tex_path, output_path)
    has_pdf = pdf_path is not None

    if not has_pdf:
        if not pdf_generator.is_pdflatex_available():
            result.setdefault("warnings", []).append(
                "PDF not generated: pdflatex is not installed or not available in PATH."
            )
        else:
            result.setdefault("warnings", []).append(
                "PDF not generated: LaTeX compilation failed. Check generated resume.tex for invalid LaTeX content."
            )

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
