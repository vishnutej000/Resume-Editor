import re


def extract_summary(latex: str) -> str:
    match = re.search(r'\\section\{Summary\}\s*(.*?)\s*\\section', latex, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_skills(latex: str) -> dict:
    pattern = re.compile(r'\\skillitem\{([^}]+)\}\{([^}]+)\}')
    return {m.group(1): m.group(2) for m in pattern.finditer(latex)}


def extract_projects(latex: str) -> list[dict]:
    projects = []
    section_match = re.search(
        r'\\section\{Projects\}(.*?)\\section\{Skills\}', latex, re.DOTALL
    )
    if section_match:
        content = section_match.group(1)
    else:
        # Projects bank may not contain section wrappers; parse the whole text.
        content = latex

    blocks = re.split(r'(?=\\textbf\{)', content)

    for block in blocks:
        name_match = re.match(r'\\textbf\{([^}]+)\}', block)
        if not name_match:
            continue
        raw_name = name_match.group(1)
        name_part = re.sub(r'\s*\(.*?\)', '', raw_name).strip()

        ts_match = re.search(r'\\textit\{Tech Stack:\s*([^}]+)\}', block)
        if not ts_match:
            # Experience entries have no Tech Stack marker.
            continue
        tech_stack = ts_match.group(1).strip() if ts_match else ""

        bullets = re.findall(r'\\item\s+(.*?)(?=\\item|\\end\{highlights\})', block, re.DOTALL)
        bullets = [b.strip() for b in bullets if b.strip()]

        projects.append({"name": name_part, "full_name": raw_name, "tech_stack": tech_stack, "bullets": bullets})

    return projects


def extract_experience(latex: str) -> dict:
    experience = {}
    for entry in extract_experience_blocks(latex):
        if entry.get("company") and entry.get("bullets"):
            experience[entry["company"]] = entry["bullets"]
    return experience


def extract_experience_blocks(latex: str) -> list[dict]:
    entries: list[dict] = []
    section_match = re.search(
        r'\\section\{Experience\}(.*?)\\section\{Projects\}', latex, re.DOTALL
    )
    if section_match:
        content = section_match.group(1)
    else:
        section_to_end = re.search(r'\\section\{Experience\}(.*)$', latex, re.DOTALL)
        content = section_to_end.group(1) if section_to_end else latex

    blocks = re.split(r'(?=\\textbf\{)', content)
    for block in blocks:
        name_match = re.match(r'\\textbf\{([^}]+)\}', block)
        if not name_match or "Tech Stack:" in block:
            continue

        begin = re.search(r'\\begin\{highlights\}', block)
        end = re.search(r'\\end\{highlights\}', block)
        if not begin or not end:
            continue

        company = name_match.group(1).strip()
        header = block[:begin.start()].rstrip()
        bullets = re.findall(r'\\item\s+(.*?)(?=\\item|\\end\{highlights\})', block, re.DOTALL)
        bullets = [b.strip() for b in bullets if b.strip()]
        if bullets:
            entries.append({"company": company, "header": header, "bullets": bullets})

    return entries


def replace_summary(latex: str, new_summary: str) -> str:
    safe_summary = escape_special_chars(new_summary)

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{safe_summary}{m.group(3)}"

    # Try Education-specific anchor first (exact match for this template).
    pattern = re.compile(
        r'(\\section\{Summary\}\s*)(.*?)(\s*\\section\{Education\})',
        re.DOTALL,
    )
    if pattern.search(latex):
        return pattern.sub(replacer, latex, count=1)

    # Fall back: any next section header.
    pattern = re.compile(
        r'(\\section\{Summary\}\s*)(.*?)(\s*\\section\{)',
        re.DOTALL,
    )
    if pattern.search(latex):
        return pattern.sub(replacer, latex, count=1)

    return latex


def replace_skills(latex: str, skills: dict) -> str:
    items = list(skills.items())
    lines = []
    for i, (cat, vals) in enumerate(items):
        suffix = r'\\[2pt]' if i < len(items) - 1 else ''
        safe_cat = escape_special_chars(cat)
        safe_vals = escape_special_chars(vals)
        lines.append(f"\\skillitem{{{safe_cat}}}{{{safe_vals}}}{suffix}")
    new_content = "\n".join(lines)

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{new_content}\n\n{m.group(3)}"

    # Try LEADERSHIP comment anchor (most precise for this template).
    pattern = re.compile(r'(\\section\{Skills\}\s*)(.*?)(\s*% --- LEADERSHIP)', re.DOTALL)
    if pattern.search(latex):
        return pattern.sub(replacer, latex, count=1)

    # Fall back: any next section header.
    pattern = re.compile(r'(\\section\{Skills\}\s*)(.*?)(\s*\\section\{)', re.DOTALL)
    if pattern.search(latex):
        return pattern.sub(replacer, latex, count=1)

    # Last resort: end of document.
    pattern = re.compile(r'(\\section\{Skills\}\s*)(.*?)(\s*\\end\{document\})', re.DOTALL)
    if pattern.search(latex):
        return pattern.sub(replacer, latex, count=1)

    return latex


def replace_project_bullets(latex: str, project_name: str, new_bullets: list[str], new_tech_stack: str) -> str:
    escaped = re.escape(project_name)
    safe_bullets = [escape_special_chars(b) for b in new_bullets]
    bullet_content = "\n    ".join(f"\\item {b}" for b in safe_bullets)

    def replacer(m):
        header = m.group(1)
        if new_tech_stack:
            safe_stack = escape_special_chars(new_tech_stack)
            header = re.sub(
                r'\\textit\{Tech Stack:[^}]+\}',
                lambda _: f"\\textit{{Tech Stack: {safe_stack}}}",
                header,
            )
        return f"{header}\n\\begin{{highlights}}\n    {bullet_content}\n\\end{{highlights}}"

    pattern = re.compile(
        r'(\\textbf\{' + escaped + r'[^}]*\}.*?)\\begin\{highlights\}.*?\\end\{highlights\}',
        re.DOTALL
    )
    return pattern.sub(replacer, latex, count=1)


def replace_projects_section(latex: str, projects: list[dict]) -> str:
    blocks: list[str] = []
    for project in projects:
        display_name = project.get("full_name") or project.get("name") or ""
        tech_stack = project.get("tech_stack", "")
        bullets = [b for b in project.get("bullets", []) if b]
        if not display_name or not bullets:
            continue

        safe_name = escape_special_chars(display_name)
        safe_stack = escape_special_chars(tech_stack)
        safe_bullets = [escape_special_chars(b) for b in bullets]
        bullet_lines = "\n".join([f"    \\item {b}" for b in safe_bullets])

        blocks.append(
            "\n".join(
                [
                    f"\\textbf{{{safe_name}}} \\hfill \\textit{{Tech Stack: {safe_stack}}}",
                    "\\begin{highlights}",
                    bullet_lines,
                    "\\end{highlights}",
                ]
            )
        )

    if not blocks:
        return latex

    new_content = "\n\n".join(blocks)
    pattern = re.compile(
        r'(\\section\{Projects\}\s*)(.*?)(\s*\\section\{Skills\})',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{new_content}\n\n{m.group(3)}"

    return pattern.sub(replacer, latex, count=1)


def replace_experience_bullets(latex: str, company: str, new_bullets: list[str]) -> str:
    escaped = re.escape(company)
    safe_bullets = [escape_special_chars(b) for b in new_bullets]
    bullet_content = "\n\\item ".join(safe_bullets)

    pattern = re.compile(
        r'(\\textbf\{' + escaped + r'\}.*?\\begin\{highlights\}\s*)(.*?)(\\end\{highlights\})',
        re.DOTALL
    )
    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}\\item {bullet_content}\n{m.group(3)}"

    return pattern.sub(replacer, latex, count=1)


def replace_experience_section(latex: str, entries: list[dict]) -> str:
    blocks: list[str] = []
    for entry in entries:
        header = entry.get("header", "").strip()
        bullets = [b for b in entry.get("bullets", []) if b]
        if not header or not bullets:
            continue

        safe_bullets = [escape_special_chars(b) for b in bullets]
        bullet_lines = "\n".join([f"\\item {b}" for b in safe_bullets])
        blocks.append(
            "\n".join([
                header,
                "\\begin{highlights}",
                bullet_lines,
                "\\end{highlights}",
            ])
        )

    if not blocks:
        return latex

    new_content = "\n\n".join(blocks)
    pattern = re.compile(
        r'(\\section\{Experience\}\s*)(.*?)(\s*\\section\{Projects\})',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{new_content}\n\n{m.group(3)}"

    return pattern.sub(replacer, latex, count=1)


def escape_special_chars(text: str) -> str:
    # Escape only unescaped LaTeX-sensitive characters to avoid double-escaping.
    text = re.sub(r'(?<!\\)&', r'\\&', text)
    text = re.sub(r'(?<!\\)%', r'\\%', text)
    text = re.sub(r'(?<!\\)\$', r'\\$', text)
    text = re.sub(r'(?<!\\)#', r'\\#', text)
    text = re.sub(r'(?<!\\)_', r'\\_', text)
    text = re.sub(r'(?<!\\)\{', r'\\{', text)
    text = re.sub(r'(?<!\\)\}', r'\\}', text)
    text = re.sub(r'(?<!\\)~', r'\\~{}', text)
    text = re.sub(r'(?<!\\)\^', r'\\^{}', text)
    return text
