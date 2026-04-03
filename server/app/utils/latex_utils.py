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
    if not section_match:
        return projects

    content = section_match.group(1)
    blocks = re.split(r'(?=\\textbf\{)', content)

    for block in blocks:
        name_match = re.match(r'\\textbf\{([^}]+)\}', block)
        if not name_match:
            continue
        raw_name = name_match.group(1)
        name_part = re.sub(r'\s*\(.*?\)', '', raw_name).strip()

        ts_match = re.search(r'\\textit\{Tech Stack:\s*([^}]+)\}', block)
        tech_stack = ts_match.group(1).strip() if ts_match else ""

        bullets = re.findall(r'\\item\s+(.*?)(?=\\item|\\end\{highlights\})', block, re.DOTALL)
        bullets = [b.strip() for b in bullets if b.strip()]

        projects.append({"name": name_part, "full_name": raw_name, "tech_stack": tech_stack, "bullets": bullets})

    return projects


def extract_experience(latex: str) -> dict:
    experience = {}
    section_match = re.search(
        r'\\section\{Experience\}(.*?)\\section\{Projects\}', latex, re.DOTALL
    )
    if not section_match:
        return experience

    content = section_match.group(1)
    blocks = re.split(r'(?=\\textbf\{)', content)

    for block in blocks:
        name_match = re.match(r'\\textbf\{([^}]+)\}', block)
        if not name_match:
            continue
        company = name_match.group(1).strip()
        bullets = re.findall(r'\\item\s+(.*?)(?=\\item|\\end\{highlights\})', block, re.DOTALL)
        bullets = [b.strip() for b in bullets if b.strip()]
        if bullets:
            experience[company] = bullets

    return experience


def replace_summary(latex: str, new_summary: str) -> str:
    safe_summary = escape_special_chars(new_summary)
    pattern = re.compile(
        r'(\\section\{Summary\}\s*)(.*?)(\s*\\section\{Education\})',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{safe_summary}{m.group(3)}"

    return pattern.sub(replacer, latex, count=1)


def replace_skills(latex: str, skills: dict) -> str:
    items = list(skills.items())
    lines = []
    for i, (cat, vals) in enumerate(items):
        suffix = r'\\[2pt]' if i < len(items) - 1 else ''
        safe_cat = escape_special_chars(cat)
        safe_vals = escape_special_chars(vals)
        lines.append(f"\\skillitem{{{safe_cat}}}{{{safe_vals}}}{suffix}")
    new_content = "\n".join(lines)

    pattern = re.compile(
        r'(\\section\{Skills\}\s*)(.*?)(\s*% --- LEADERSHIP)',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return f"{m.group(1)}{new_content}\n\n{m.group(3)}"

    return pattern.sub(replacer, latex, count=1)


def replace_project_by_slot(
    latex: str,
    slot_index: int,
    new_name: str,
    new_tech_stack: str,
    new_bullets: list[str],
) -> str:
    """Replace the entire Nth project block (0-indexed) with new content.

    Used when the AI picks a *different* project from the bank for a slot.
    The old project name/header is fully replaced so swaps actually work.
    """
    section_match = re.search(
        r'(\\section\{Projects\})(.*?)(\\section\{Skills\})',
        latex,
        re.DOTALL,
    )
    if not section_match:
        return latex

    projects_content = section_match.group(2)

    # Split into individual project blocks, keeping the \textbf{ delimiter
    raw_blocks = re.split(r'(?=\\textbf\{)', projects_content)
    project_blocks = [b for b in raw_blocks if re.match(r'\\textbf\{', b.strip())]
    non_project_prefix = raw_blocks[0] if not re.match(r'\\textbf\{', raw_blocks[0].strip()) else ""

    if slot_index >= len(project_blocks):
        return latex  # slot out of range, leave unchanged

    # Build the replacement block
    safe_name = escape_special_chars(new_name)
    safe_stack = escape_special_chars(new_tech_stack)
    safe_bullets = [escape_special_chars(b) for b in new_bullets]
    bullet_content = "\n    ".join(f"\\item {b}" for b in safe_bullets)
    new_block = (
        f"\\textbf{{{safe_name}}} \\hfill \\textit{{Tech Stack: {safe_stack}}}\n"
        f"\\begin{{highlights}}\n    {bullet_content}\n\\end{{highlights}}\n"
    )

    project_blocks[slot_index] = new_block
    new_projects_content = non_project_prefix + "".join(project_blocks)

    before = latex[: section_match.start(2)]
    after = latex[section_match.end(2) :]
    return before + new_projects_content + after


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
