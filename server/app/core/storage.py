import json
import re
import uuid
import aiofiles
from pathlib import Path
from datetime import datetime
from app.config import settings


def load_base_resume() -> str:
    return Path(settings.BASE_RESUME_PATH).read_text(encoding="utf-8")


def load_projects_bank() -> str:
    return Path(settings.PROJECTS_BANK_PATH).read_text(encoding="utf-8")


def load_experience_bank() -> str:
    return Path(settings.EXPERIENCE_BANK_PATH).read_text(encoding="utf-8")


def make_folder_name(company: str, role: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d")
    clean = lambda s: re.sub(r'[^a-zA-Z0-9]', '', s)[:20]
    short_id = str(uuid.uuid4())[:6]
    return f"{date}_{clean(company)}_{clean(role)}_{short_id}"


def get_output_path(folder_name: str) -> Path:
    path = Path(settings.OUTPUTS_DIR) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_run(
    folder_name: str,
    latex: str,
    jd_text: str,
    analysis: dict,
    changes: dict,
    structured_data: dict = None,
) -> Path:
    output_path = get_output_path(folder_name)

    async with aiofiles.open(output_path / "resume.tex", "w", encoding="utf-8") as f:
        await f.write(latex)

    async with aiofiles.open(output_path / "jd.txt", "w", encoding="utf-8") as f:
        await f.write(jd_text)

    async with aiofiles.open(output_path / "analysis.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(analysis, indent=2))

    async with aiofiles.open(output_path / "changes.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(changes, indent=2))
        
    if structured_data:
        async with aiofiles.open(output_path / "structured_data.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(structured_data, indent=2))

    return output_path


def folder_exists(folder_name: str) -> bool:
    return (Path(settings.OUTPUTS_DIR) / folder_name).exists()


def get_file_path(folder_name: str, filename: str) -> Path:
    return Path(settings.OUTPUTS_DIR) / folder_name / filename
