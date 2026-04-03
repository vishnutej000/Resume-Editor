import logging
import shutil
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pathlib import Path
from app.api.routes import health, resume, history, providers
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Resume Editor API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(resume.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(providers.router, prefix="/api")

Path(settings.OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root():
    outputs_path = Path(settings.OUTPUTS_DIR)
    data_path = Path(settings.DATA_DIR)

    total_apps = 0
    try:
        from app.db import duckdb_client
        total_apps = duckdb_client.count_applications()
    except Exception as e:
        logger.warning("DuckDB unavailable on root endpoint: %s", e)

    duckdb_file = data_path / "resume_editor.duckdb"
    lancedb_dir = data_path / "lancedb"

    outputs_count = len(list(outputs_path.iterdir())) if outputs_path.exists() else 0
    outputs_size = sum(f.stat().st_size for f in outputs_path.rglob("*") if f.is_file()) if outputs_path.exists() else 0
    outputs_size_mb = round(outputs_size / (1024 * 1024), 2)

    duckdb_ok = duckdb_file.exists()
    lancedb_ok = lancedb_dir.exists()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    def badge(ok: bool, yes="OK", no="MISSING"):
        color = "#3fb950" if ok else "#f85149"
        label = yes if ok else no
        return f'<span style="background:#0d2a1a;color:{color};border:1px solid {color};padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;">{label}</span>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resume Editor — Status</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh;padding:40px 24px}}
  h1{{font-size:24px;font-weight:700;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:14px;margin-bottom:32px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:32px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px}}
  .card-label{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin-bottom:8px}}
  .card-value{{font-size:28px;font-weight:700;color:#58a6ff}}
  .card-sub{{font-size:12px;color:#8b949e;margin-top:4px}}
  .section{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:16px}}
  .section-title{{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin-bottom:16px}}
  .row{{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid #21262d}}
  .row:last-child{{border-bottom:none}}
  .row-label{{font-size:13px;color:#c9d1d9}}
  .row-value{{font-size:13px;color:#8b949e;display:flex;align-items:center;gap:10px}}
  .endpoint{{font-family:monospace;background:#21262d;padding:3px 8px;border-radius:4px;font-size:12px}}
  .method{{font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;margin-right:6px}}
  .get{{background:#0d2a1a;color:#3fb950}}
  .post{{background:#0d1f2a;color:#58a6ff}}
  .delete{{background:#2a0d0d;color:#f85149}}
  footer{{text-align:center;color:#8b949e;font-size:12px;margin-top:32px}}
</style>
</head>
<body>
<h1>📄 Resume Editor API</h1>
<div class="sub">Server status as of {now}</div>

<div class="grid">
  <div class="card">
    <div class="card-label">Total Applications</div>
    <div class="card-value">{total_apps}</div>
    <div class="card-sub">Tailored resumes generated</div>
  </div>
  <div class="card">
    <div class="card-label">Output Folders</div>
    <div class="card-value">{outputs_count}</div>
    <div class="card-sub">{outputs_size_mb} MB used on disk</div>
  </div>
  <div class="card">
    <div class="card-label">Active Model</div>
    <div class="card-value" style="font-size:14px;padding-top:6px">{settings.MODEL}</div>
    <div class="card-sub">Provider: {settings.PROVIDER}</div>
  </div>
  <div class="card">
    <div class="card-label">Fallback Model</div>
    <div class="card-value" style="font-size:14px;padding-top:6px">{settings.FALLBACK_MODEL or "Not set"}</div>
    <div class="card-sub">{"Configured" if settings.FALLBACK_MODEL else "No fallback configured"}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Services</div>
  <div class="row">
    <div class="row-label">API Server</div>
    <div class="row-value">{badge(True, "Running")}</div>
  </div>
  <div class="row">
    <div class="row-label">DuckDB (metadata)</div>
    <div class="row-value"><span style="color:#8b949e;font-size:12px">{str(duckdb_file)}</span> &nbsp; {badge(duckdb_ok, "Initialized", "Not created yet")}</div>
  </div>
  <div class="row">
    <div class="row-label">LanceDB (semantic search)</div>
    <div class="row-value"><span style="color:#8b949e;font-size:12px">{str(lancedb_dir)}</span> &nbsp; {badge(lancedb_ok, "Initialized", "Not created yet")}</div>
  </div>
  <div class="row">
    <div class="row-label">PDF Generator (pdflatex)</div>
    <div class="row-value">{badge(shutil.which("pdflatex") is not None, "Available", "Not installed — PDFs disabled")}</div>
  </div>
  <div class="row">
    <div class="row-label">Outputs Directory</div>
    <div class="row-value"><span style="color:#8b949e;font-size:12px">{str(outputs_path.resolve())}</span> &nbsp; {badge(outputs_path.exists())}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">API Endpoints</div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/health</span></div>
    <div class="row-value">Server health + model info</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/api/providers</span></div>
    <div class="row-value">All supported providers and models</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method post">POST</span><span class="endpoint">/api/analyze-jd</span></div>
    <div class="row-value">Analyze a job description</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method post">POST</span><span class="endpoint">/api/tailor-resume</span></div>
    <div class="row-value">Tailor resume for a job — main endpoint</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/api/history</span></div>
    <div class="row-value">List all past applications</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method post">POST</span><span class="endpoint">/api/history/search</span></div>
    <div class="row-value">Semantic search over past JDs</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/api/history/{{id}}/pdf</span></div>
    <div class="row-value">Download PDF for an application</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/api/history/{{id}}/latex</span></div>
    <div class="row-value">Download .tex file for an application</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method delete">DELETE</span><span class="endpoint">/api/history/{{id}}</span></div>
    <div class="row-value">Delete an application and its files</div>
  </div>
  <div class="row">
    <div class="row-label"><span class="method get">GET</span><span class="endpoint">/docs</span></div>
    <div class="row-value">Interactive Swagger API documentation</div>
  </div>
</div>

<footer>Resume Editor v1.0.0 &nbsp;·&nbsp; <a href="/docs" style="color:#58a6ff">API Docs</a></footer>
</body>
</html>"""
    return html
