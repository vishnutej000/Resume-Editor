import re
import lancedb
import numpy as np
import pyarrow as pa
from pathlib import Path
from fastembed import TextEmbedding
from app.config import settings

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

_db = None
_table = None
_embedder: TextEmbedding | None = None

TABLE_NAME = "jd_embeddings"


def _get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder


def _get_table():
    global _db, _table
    if _table is None:
        db_path = Path(settings.DATA_DIR) / "lancedb"
        db_path.mkdir(parents=True, exist_ok=True)
        _db = lancedb.connect(str(db_path))
        if TABLE_NAME in _db.table_names():
            _table = _db.open_table(TABLE_NAME)
        else:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("company", pa.string()),
                pa.field("role", pa.string()),
                pa.field("jd_text", pa.string()),
                pa.field("created_at", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 384)),
            ])
            _table = _db.create_table(TABLE_NAME, schema=schema)
    return _table


def embed_text(text: str) -> list[float]:
    embedder = _get_embedder()
    vectors = list(embedder.embed([text]))
    return vectors[0].tolist()


def add_jd_embedding(app_id: str, company: str, role: str, jd_text: str, created_at: str):
    table = _get_table()
    vector = embed_text(f"{role} {company} {jd_text[:2000]}")
    table.add([{
        "id": app_id,
        "company": company,
        "role": role,
        "jd_text": jd_text[:3000],
        "created_at": created_at,
        "vector": vector,
    }])


def search_similar(query: str, limit: int = 5) -> list[dict]:
    table = _get_table()
    vector = embed_text(query)
    results = table.search(vector).limit(limit).to_list()
    return [
        {"id": r["id"], "company": r["company"], "role": r["role"],
         "created_at": r["created_at"], "score": float(r.get("_distance", 0))}
        for r in results
    ]


def delete_embedding(app_id: str):
    if not _UUID_RE.match(app_id):
        return
    table = _get_table()
    table.delete(f"id = '{app_id}'")
