import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
PDF_COMPILE_TIMEOUT_SECONDS = 300


LATEX_ENGINES = ["pdflatex", "xelatex", "lualatex", "tectonic"]


def _resolve_engine_path(engine: str) -> str | None:
    direct = shutil.which(engine)
    if direct:
        return direct

    # On Windows, MiKTeX may be installed under Local Programs before PATH refresh.
    exe_name = f"{engine}.exe"
    home = Path.home()
    windows_candidates = [
        home / "AppData" / "Local" / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / exe_name,
        Path("C:/Program Files/MiKTeX/miktex/bin/x64") / exe_name,
    ]
    for candidate in windows_candidates:
        if candidate.exists():
            return str(candidate)

    return None


def get_available_engine() -> str | None:
    for engine in LATEX_ENGINES:
        if _resolve_engine_path(engine):
            return engine
    return None


def is_pdflatex_available() -> bool:
    return _resolve_engine_path("pdflatex") is not None


def is_latex_compiler_available() -> bool:
    return get_available_engine() is not None


async def generate(tex_path: Path, output_dir: Path) -> Path | None:
    engine = get_available_engine()
    if not engine:
        return None
    executable = _resolve_engine_path(engine)
    if not executable:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    if engine == "tectonic":
        cmd = [
            executable,
            "--outdir",
            str(output_dir),
            str(tex_path),
        ]
    else:
        cmd = [
            executable,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={output_dir}",
            str(tex_path),
        ]

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PDF_COMPILE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out_text = (exc.stdout or b"").decode("utf-8", errors="ignore")
        err_text = (exc.stderr or b"").decode("utf-8", errors="ignore")
        merged_output = (out_text + "\n" + err_text).strip()
        if merged_output:
            try:
                (output_dir / "compile_output.log").write_text(merged_output, encoding="utf-8")
            except Exception:
                logger.debug("Unable to write compile_output.log for %s", tex_path)
        logger.warning("%s timed out after %ds for %s", engine, PDF_COMPILE_TIMEOUT_SECONDS, tex_path)
        return None
    except Exception as e:
        logger.exception("Compiler execution failed for %s using %s: %s", tex_path, engine, e)
        return None

    out_text = (completed.stdout or b"").decode("utf-8", errors="ignore")
    err_text = (completed.stderr or b"").decode("utf-8", errors="ignore")
    merged_output = (out_text + "\n" + err_text).strip()
    if merged_output:
        log_path = output_dir / "compile_output.log"
        try:
            log_path.write_text(merged_output, encoding="utf-8")
        except Exception:
            logger.debug("Unable to write compile_output.log for %s", tex_path)

    if completed.returncode != 0:
        tail = "\n".join(merged_output.splitlines()[-12:]) if merged_output else "(no compiler output)"
        logger.warning("%s failed for %s (exit=%s): %s", engine, tex_path, completed.returncode, tail)
        return None

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    return pdf_path if pdf_path.exists() else None
