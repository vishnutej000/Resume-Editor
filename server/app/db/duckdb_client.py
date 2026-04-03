import duckdb
import json
from pathlib import Path
from datetime import datetime
from app.config import settings

_conn: duckdb.DuckDBPyConnection | None = None


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        db_path = Path(settings.DATA_DIR) / "resume_editor.duckdb"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(db_path))
        _init_schema(_conn)
    return _conn


def _init_schema(conn: duckdb.DuckDBPyConnection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id VARCHAR PRIMARY KEY,
            company VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL,
            folder_name VARCHAR NOT NULL,
            has_pdf BOOLEAN DEFAULT FALSE,
            jd_preview VARCHAR,
            change_rationale VARCHAR,
            keywords_covered JSON,
            keywords_missing JSON,
            warnings JSON
        )
    """)


def insert_application(record: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        record["id"],
        record["company"],
        record["role"],
        record["created_at"],
        record["folder_name"],
        record["has_pdf"],
        record["jd_preview"],
        record["change_rationale"],
        json.dumps(record.get("keywords_covered", [])),
        json.dumps(record.get("keywords_missing", [])),
        json.dumps(record.get("warnings", [])),
    ])


def list_applications(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, company, role, created_at, folder_name, has_pdf, jd_preview, warnings
        FROM applications
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [limit, offset]).fetchall()

    return [
        {
            "id": r[0], "company": r[1], "role": r[2],
            "created_at": r[3], "folder_name": r[4],
            "has_pdf": r[5], "jd_preview": r[6],
            "warnings_count": len(json.loads(r[7] or "[]")),
        }
        for r in rows
    ]


def count_applications() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]


def get_application(app_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", [app_id]
    ).fetchone()
    if not row:
        return None
    cols = ["id", "company", "role", "created_at", "folder_name", "has_pdf",
            "jd_preview", "change_rationale", "keywords_covered", "keywords_missing", "warnings"]
    return dict(zip(cols, row))


def delete_application(app_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM applications WHERE id = ?", [app_id])


def update_pdf_status(app_id: str, has_pdf: bool):
    conn = get_conn()
    conn.execute("UPDATE applications SET has_pdf = ? WHERE id = ?", [has_pdf, app_id])


def search_applications(query: str, limit: int = 20) -> list[dict]:
    conn = get_conn()
    pattern = f"%{query}%"
    rows = conn.execute("""
        SELECT id, company, role, created_at, folder_name, has_pdf, jd_preview, warnings
        FROM applications
        WHERE company ILIKE ? OR role ILIKE ? OR jd_preview ILIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """, [pattern, pattern, pattern, limit]).fetchall()
    return [
        {
            "id": r[0], "company": r[1], "role": r[2],
            "created_at": r[3], "folder_name": r[4],
            "has_pdf": r[5], "jd_preview": r[6],
            "warnings_count": len(json.loads(r[7] or "[]")),
        }
        for r in rows
    ]
