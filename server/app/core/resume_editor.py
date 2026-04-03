import re
from difflib import SequenceMatcher

from app.core.ai_client import call_ai, parse_json
from app.core import latex_guard
from app.utils import latex_utils
from app.prompts import resume_edit as prompt


OBVIOUS_TARGETING_PATTERNS = [
    re.compile(r"\bfor\s+(this|the)\s+(role|position|job)\b", re.IGNORECASE),
    re.compile(r"\baligned\s+with\s+(the\s+)?job\s+description\b", re.IGNORECASE),
    re.compile(r"\bto\s+match\s+(the\s+)?jd\b", re.IGNORECASE),
    re.compile(r"\bats[-\s]?optimized\b", re.IGNORECASE),
    re.compile(r"\bkeyword[-\s]?rich\b", re.IGNORECASE),
]

TECHNICAL_SOFT_SKILL_HINTS = {
    "api", "apis", "backend", "frontend", "fullstack", "python", "java", "golang",
    "typescript", "javascript", "sql", "docker", "kubernetes", "terraform", "linux",
    "cloud", "devops", "fastapi", "react", "node", "flutter", "mongodb", "postgresql",
    "firebase", "nlp", "ai", "ml", "lora", "oop", "sdlc", "ci/cd", "ci", "cd",
    "rest", "restful", "keyword", "ats",
}

CANONICAL_SOFT_SKILLS = [
    "Leadership",
    "Teamwork",
    "Communication",
    "Collaboration",
    "Active Listening",
    "Empathy",
    "Time Management",
]

SOFT_SKILL_ALIASES = {
    "leadership": "Leadership",
    "teamwork": "Teamwork",
    "team work": "Teamwork",
    "communication": "Communication",
    "collaboration": "Collaboration",
    "active listening": "Active Listening",
    "listening": "Active Listening",
    "empathy": "Empathy",
    "time management": "Time Management",
}

DISCOURAGED_SOFT_SKILLS = {
    "problem solving",
    "problem-solving",
    "continuous learning",
    "adaptability",
    "ownership",
    "mentorship",
    "stakeholder management",
}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _remove_obvious_targeting(text: str) -> str:
    cleaned = text or ""
    for pattern in OBVIOUS_TARGETING_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    return _normalize_ws(cleaned)


def _choose_subtle_summary(current_summary: str, candidate_summary: str) -> str:
    current = _normalize_ws(current_summary)
    candidate = _remove_obvious_targeting(candidate_summary)

    if not candidate:
        return current

    if len(candidate.split()) > max(1, int(len(current.split()) * 1.2)):
        return current

    similarity = SequenceMatcher(None, current.lower(), candidate.lower()).ratio()
    if similarity < 0.55:
        return current

    return candidate


def _split_csv_items(text: str) -> list[str]:
    return [item.strip() for item in (text or "").split(",") if item.strip()]


def _is_real_soft_skill(item: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s/+\-]", "", item.lower()).strip()
    if not normalized:
        return False
    tokens = set(re.split(r"[\s/+\-]+", normalized))
    if not tokens:
        return False
    return not any(token in TECHNICAL_SOFT_SKILL_HINTS for token in tokens)


def _normalize_soft_skill(item: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", item.strip())
    key = cleaned.lower()
    if key in DISCOURAGED_SOFT_SKILLS:
        return None
    return SOFT_SKILL_ALIASES.get(key)


def _sanitize_soft_skills(candidate: str, current: str) -> str:
    source = _split_csv_items(candidate) + _split_csv_items(current)
    chosen: list[str] = []

    for item in source:
        if not _is_real_soft_skill(item):
            continue
        normalized = _normalize_soft_skill(item)
        if normalized and normalized not in chosen:
            chosen.append(normalized)

    # Always guarantee these core interpersonal skills.
    for required in ["Leadership", "Teamwork", "Communication"]:
        if required not in chosen:
            chosen.insert(0, required)

    # Keep only approved interpersonal skills and stable order.
    final = [skill for skill in CANONICAL_SOFT_SKILLS if skill in chosen]
    if len(final) < 5:
        for skill in CANONICAL_SOFT_SKILLS:
            if skill not in final:
                final.append(skill)
            if len(final) == 5:
                break

    return ", ".join(final[:5])


async def tailor(
    latex_resume: str,
    projects_bank: str,
    experience_bank: str,
    jd_analysis: dict,
    target_domain: str | None,
) -> dict:
    current_summary = latex_utils.extract_summary(latex_resume)
    current_skills = latex_utils.extract_skills(latex_resume)
    current_projects = latex_utils.extract_projects(latex_resume)
    current_experience = latex_utils.extract_experience(latex_resume)

    messages = [
        {"role": "system", "content": prompt.SYSTEM},
        {"role": "user", "content": prompt.build_user(
            jd_analysis=jd_analysis,
            projects_bank=projects_bank,
            experience_bank=experience_bank,
            current_summary=current_summary,
            current_skills=current_skills,
            current_projects=current_projects,
            current_experience=current_experience,
            target_domain=target_domain,
        )},
    ]

    raw = await call_ai(messages, json_mode=True)
    result = parse_json(raw)

    updated_latex = _apply_changes(
        latex_resume,
        result,
        current_projects,
        current_summary,
        current_skills,
    )

    issues = latex_guard.validate(updated_latex)
    if issues:
        result.setdefault("warnings", []).extend(issues)

    result["updated_latex"] = updated_latex
    return result


def _apply_changes(
    latex: str,
    result: dict,
    original_projects: list[dict],
    current_summary: str,
    current_skills: dict,
) -> str:
    if result.get("tailored_summary"):
        subtle_summary = _choose_subtle_summary(current_summary, result["tailored_summary"])
        result["tailored_summary"] = subtle_summary
        latex = latex_utils.replace_summary(latex, subtle_summary)

    if result.get("tailored_skills") and isinstance(result["tailored_skills"], dict):
        tailored_skills = result["tailored_skills"]
        tailored_soft = tailored_skills.get("Soft Skills", "")
        current_soft = current_skills.get("Soft Skills", "")
        tailored_skills["Soft Skills"] = _sanitize_soft_skills(tailored_soft, current_soft)
        latex = latex_utils.replace_skills(latex, result["tailored_skills"])

    tailored_projects = result.get("tailored_projects", [])
    for slot_index, proj in enumerate(tailored_projects):
        name = proj.get("name", "")
        cleaned_bullets = [_remove_obvious_targeting(b) for b in proj.get("bullets", [])]
        cleaned_bullets = [b for b in cleaned_bullets if b]

        original = next((p for p in original_projects if p["name"] == name), None)

        if original is None:
            # The AI picked a project from the bank that isn't currently on the resume —
            # this is a genuine swap. Replace the entire slot block by position.
            latex = latex_utils.replace_project_by_slot(
                latex,
                slot_index,
                new_name=name,
                new_tech_stack=proj.get("tech_stack", ""),
                new_bullets=cleaned_bullets,
            )
        else:
            # Project is already on the resume — just update bullets/tech stack in-place.
            full_name = original.get("full_name", name)
            latex = latex_utils.replace_project_bullets(
                latex,
                full_name,
                cleaned_bullets,
                proj.get("tech_stack", ""),
            )

    for company, bullets in result.get("tailored_experience", {}).items():
        cleaned_bullets = [_remove_obvious_targeting(b) for b in bullets]
        cleaned_bullets = [b for b in cleaned_bullets if b]
        if cleaned_bullets:
            latex = latex_utils.replace_experience_bullets(latex, company, cleaned_bullets)

    return latex
