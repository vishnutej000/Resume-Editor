import json
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import aiofiles
from app.models.response import HistoryResponse, ApplicationRecord, TailorResumeResponse, JDAnalysis
from app.models.request import SearchHistoryRequest
from app.db import duckdb_client, lancedb_client
from app.core import storage
from app.config import settings

router = APIRouter()


@router.get("/history", response_model=HistoryResponse)
async def get_history(limit: int = 50, offset: int = 0):
    apps = duckdb_client.list_applications(limit=limit, offset=offset)
    total = duckdb_client.count_applications()
    return HistoryResponse(
        total=total,
        applications=[ApplicationRecord(**a) for a in apps],
    )


@router.post("/history/search")
async def search_history(req: SearchHistoryRequest):
    if settings.SEMANTIC_SEARCH:
        try:
            results = lancedb_client.search_similar(req.query, limit=req.limit)
            return {"results": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        results = duckdb_client.search_applications(req.query, limit=req.limit)
        return {"results": results}


@router.get("/history/{app_id}/pdf")
async def download_pdf(app_id: str):
    record = duckdb_client.get_application(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    pdf_path = storage.get_file_path(record["folder_name"], "resume.pdf")
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not generated for this application")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{record['company']}_{record['role']}_resume.pdf",
    )


@router.get("/history/{app_id}/latex")
async def download_latex(app_id: str):
    record = duckdb_client.get_application(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    tex_path = storage.get_file_path(record["folder_name"], "resume.tex")
    if not tex_path.exists():
        raise HTTPException(status_code=404, detail="LaTeX file not found")

    return FileResponse(
        path=str(tex_path),
        media_type="text/plain",
        filename=f"{record['company']}_{record['role']}_resume.tex",
    )


@router.get("/history/{app_id}/analysis")
async def get_analysis(app_id: str):
    record = duckdb_client.get_application(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    analysis_path = storage.get_file_path(record["folder_name"], "analysis.json")
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Analysis file not found")

    async with aiofiles.open(analysis_path, "r") as f:
        content = await f.read()
    return json.loads(content)


@router.get("/history/{app_id}", response_model=TailorResumeResponse)
async def get_application_details(app_id: str):
    record = duckdb_client.get_application(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    folder_name = record["folder_name"]
    
    # Read files
    try:
        async with aiofiles.open(storage.get_file_path(folder_name, "analysis.json"), "r") as f:
            jd_analysis = json.loads(await f.read())
    except Exception:
        jd_analysis = {}

    try:
        async with aiofiles.open(storage.get_file_path(folder_name, "changes.json"), "r") as f:
            changes = json.loads(await f.read())
    except Exception:
        changes = {}

    try:
        async with aiofiles.open(storage.get_file_path(folder_name, "resume.tex"), "r", encoding="utf-8") as f:
            updated_latex = await f.read()
    except Exception:
        updated_latex = ""

    structured_data = {}
    try:
        async with aiofiles.open(storage.get_file_path(folder_name, "structured_data.json"), "r") as f:
            structured_data = json.loads(await f.read())
    except Exception:
        pass

    return TailorResumeResponse(
        id=record["id"],
        company=record["company"],
        role=record["role"],
        jd_analysis=JDAnalysis(**jd_analysis) if jd_analysis else JDAnalysis(
            target_role="", must_have_skills=[], preferred_skills=[],
            responsibilities=[], domain="", experience_level="",
            ats_keywords=[], summary=""
        ),
        tailored_summary=structured_data.get("tailored_summary", ""),
        tailored_skills=structured_data.get("tailored_skills", {}),
        tailored_projects=structured_data.get("tailored_projects", []),
        tailored_experience=structured_data.get("tailored_experience", {}),
        updated_latex=updated_latex,
        keyword_coverage=changes.get("keyword_coverage", {}),
        change_rationale=changes.get("change_rationale", ""),
        warnings=changes.get("warnings", []),
        pdf_available=record["has_pdf"],
        folder_name=folder_name,
        created_at=record["created_at"],
    )


@router.delete("/history/{app_id}")
async def delete_application(app_id: str):
    record = duckdb_client.get_application(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    outputs_root = Path(settings.OUTPUTS_DIR).resolve()
    folder_path = (outputs_root / record["folder_name"]).resolve()
    if outputs_root in folder_path.parents and folder_path.exists():
        shutil.rmtree(str(folder_path), ignore_errors=True)

    duckdb_client.delete_application(app_id)

    if settings.SEMANTIC_SEARCH:
        try:
            lancedb_client.delete_embedding(app_id)
        except Exception:
            pass

    return {"deleted": True, "id": app_id}
