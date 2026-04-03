import re
from difflib import SequenceMatcher

from app.core.ai_client import call_ai_complex, parse_json
from app.core import latex_guard
from app.utils import latex_utils
from app.prompts import resume_edit as prompt
from app.config import settings


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

    for required in ["Leadership", "Teamwork", "Communication"]:
        if required not in chosen:
            chosen.insert(0, required)

    final = [skill for skill in CANONICAL_SOFT_SKILLS if skill in chosen]
    if len(final) < 5:
        for skill in CANONICAL_SOFT_SKILLS:
            if skill not in final:
                final.append(skill)
            if len(final) == 5:
                break

    return ", ".join(final[:5])


# ── Pre-ranking: score each bank entry against JD keywords before LLM call ──

def _tokenize_for_rank(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _score_entry(entry_text: str, jd_tokens: set[str]) -> int:
    """Count how many JD keyword tokens appear in the entry text."""
    entry_tokens = _tokenize_for_rank(entry_text)
    return len(jd_tokens & entry_tokens)


def _build_jd_tokens(jd_analysis: dict) -> set[str]:
    """Build a flat token set from all JD signals for scoring."""
    parts = (
        jd_analysis.get("must_have_skills", [])
        + jd_analysis.get("preferred_skills", [])
        + jd_analysis.get("ats_keywords", [])
        + jd_analysis.get("responsibilities", [])
    )
    return _tokenize_for_rank(" ".join(parts))


def _rank_projects(bank_text: str, jd_analysis: dict, n_slots: int) -> str:
    """
    Parse the projects bank, score each project against JD tokens,
    return the top (n_slots * PROJECT_CANDIDATE_MULTIPLIER) as plain text.
    Prevents the LLM from seeing irrelevant projects and picking randomly.
    """
    all_projects = latex_utils.extract_projects(bank_text)
    if not all_projects:
        return bank_text  # fallback: return raw if parsing fails

    jd_tokens = _build_jd_tokens(jd_analysis)
    limit = n_slots * settings.PROJECT_CANDIDATE_MULTIPLIER

    scored = []
    for proj in all_projects:
        combined = " ".join([
            proj.get("name", ""),
            proj.get("tech_stack", ""),
            " ".join(proj.get("bullets", [])),
        ])
        scored.append((_score_entry(combined, jd_tokens), proj))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    lines = []
    for _, proj in top:
        lines.append(f"Project: {proj['full_name']}")
        lines.append(f"Tech Stack: {proj['tech_stack']}")
        for b in proj.get("bullets", []):
            lines.append(f"  - {b}")
        lines.append("")
    return "\n".join(lines)


def _rank_experience(bank_text: str, jd_analysis: dict) -> str:
    """
    Parse the experience bank, score each company block against JD tokens,
    return all entries sorted by relevance.
    """
    all_exp = latex_utils.extract_experience(bank_text)
    if not all_exp:
        return bank_text

    jd_tokens = _build_jd_tokens(jd_analysis)

    scored = []
    for company, bullets in all_exp.items():
        combined = company + " " + " ".join(bullets)
        scored.append((_score_entry(combined, jd_tokens), company, bullets))

    scored.sort(key=lambda x: x[0], reverse=True)

    lines = []
    for _, company, bullets in scored:
        lines.append(f"Company: {company}")
        for b in bullets:
            lines.append(f"  - {b}")
        lines.append("")
    return "\n".join(lines)


# ── Real ATS score: computed in Python after tailoring, never hallucinated ──

def _compute_ats_score(tailored_latex: str, ats_keywords: list[str]) -> dict:
    """
    Strip LaTeX commands, then deterministically check which ATS keywords
    from the JD appear in the resume text. Returns score 0-100.
    """
    plain = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^}]*)\}', r'\2', tailored_latex)
    plain = re.sub(r'\\[a-zA-Z]+\*?', ' ', plain)
    plain = plain.lower()

    matched = []
    missing = []
    for kw in ats_keywords:
        kw_clean = kw.lower().strip()
        if kw_clean in plain:
            matched.append(kw)
        else:
            # All significant tokens of the keyword must appear somewhere
            tokens = [t for t in re.split(r"[\s/+\-.,]+", kw_clean) if len(t) > 2]
            if tokens and all(t in plain for t in tokens):
                matched.append(kw)
            else:
                missing.append(kw)

    total = len(ats_keywords)
    score = round(len(matched) / total * 100) if total > 0 else 0

    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "total_keywords": total,
    }


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

    n_slots = len(current_projects)

    # Pre-rank banks — LLM only sees the most relevant candidates
    ranked_projects_bank = _rank_projects(projects_bank, jd_analysis, n_slots)
    ranked_experience_bank = _rank_experience(experience_bank, jd_analysis)

    messages = [
        {"role": "system", "content": prompt.SYSTEM},
        {"role": "user", "content": prompt.build_user(
            jd_analysis=jd_analysis,
            projects_bank=ranked_projects_bank,
            experience_bank=ranked_experience_bank,
            current_summary=current_summary,
            current_skills=current_skills,
            current_projects=current_projects,
            current_experience=current_experience,
            target_domain=target_domain,
        )},
    ]

    # DeepSeek V3 via NVIDIA — temperature=0.0 set globally in config
    raw = await call_ai_complex(messages, json_mode=True)
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

    # Real ATS score — computed deterministically in Python, not by the model
    result["ats_score"] = _compute_ats_score(updated_latex, jd_analysis.get("ats_keywords", []))

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

    for proj in result.get("tailored_projects", []):
        name = proj.get("name", "")
        original = next((p for p in original_projects if p["name"] == name), None)
        full_name = original.get("full_name", name) if original else name
        cleaned_bullets = [_remove_obvious_targeting(b) for b in proj.get("bullets", [])]
        cleaned_bullets = [b for b in cleaned_bullets if b]
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
