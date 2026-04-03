import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def is_pdflatex_available() -> bool:
    return shutil.which("pdflatex") is not None


async def generate(tex_path: Path, output_dir: Path) -> Path | None:
    if not is_pdflatex_available():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("pdflatex timed out after %ds for %s", 120, tex_path)
        return None

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    return pdf_path if pdf_path.exists() else None
