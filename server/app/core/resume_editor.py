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

LANGUAGE_HINTS = {
    "python", "java", "javascript", "typescript", "go", "golang", "sql", "dart",
    "bash", "shell", "rust", "kotlin", "swift", "c", "c++", "c#",
}
FRAMEWORK_HINTS = {
    "fastapi", "flask", "django", "spring", "react", "next", "next.js", "node",
    "express", "flutter", "react native", "angular", "vue", "tensorflow", "pytorch",
}
DATABASE_HINTS = {
    "postgres", "postgresql", "mysql", "mongodb", "redis", "firebase", "dynamodb",
    "database", "databases", "sqlite", "vector db", "vector databases",
}
CLOUD_DEVOPS_HINTS = {
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "linux", "ci/cd",
    "devops", "helm", "cloud", "git",
}

NON_SKILL_PHRASE_HINTS = {
    "degree",
    "related field",
    "willingness",
    "ability to",
    "abilities",
    "communication and teamwork",
    "project experience",
    "internship",
    "strong problem-solving",
    "attention to detail",
    "software applications",
    "knowledge of",
    "previous",
    # vague phrases that appear in JDs but are not stackable skills
    "computer science",
    "code review",
    "code reviews",
    "best practice",
    "best practices",
    "version control system",
    "version control systems",
    "software development",
    "software engineering",
    "problem solving",
    "analytical skill",
}

TECH_SIGNAL_HINTS = LANGUAGE_HINTS | FRAMEWORK_HINTS | DATABASE_HINTS | CLOUD_DEVOPS_HINTS | {
    "api", "rest", "restful", "testing", "automation", "debugging", "microservices",
    "distributed", "grpc", "oop", "sdlc", "git", "version control", "c++", "c#",
    ".net", "spring", "redis", "graphql", "numpy", "pandas",
}

MAX_SUMMARY_WORDS = 38
MAX_BULLET_WORDS = 24


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim_to_word_limit(text: str, max_words: int) -> str:
    words = _normalize_ws(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


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

    # Only apply word-limit and similarity gates when there is an existing summary to protect.
    # If current is empty, accept any non-empty candidate.
    if current:
        if len(candidate.split()) > max(1, int(len(current.split()) * 1.2)):
            return current
        similarity = SequenceMatcher(None, current.lower(), candidate.lower()).ratio()
        if similarity < 0.55:
            return current

    return candidate


def _split_csv_items(text: str) -> list[str]:
    return [item.strip() for item in (text or "").split(",") if item.strip()]


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _normalize_ws(item)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _normalize_skill_key(skill: str) -> str:
    # Preserve + and # so C++/C# are not collapsed to the same key as "c"
    return re.sub(r"[^a-z0-9+#]+", " ", (skill or "").lower()).strip()


def _build_skill_presence_set(skills_map: dict[str, str]) -> set[str]:
    present: set[str] = set()
    for value in skills_map.values():
        for item in _split_csv_items(value):
            key = _normalize_skill_key(item)
            if key:
                present.add(key)
    return present


def _skill_tokens(text: str) -> set[str]:
    """Extract lowercase word tokens from a skill string (handles c++, ci/cd, next.js etc.)."""
    return set(re.findall(r'[a-z0-9][a-z0-9+#./]*', text.lower()))


def _hint_matches(hint: str, low: str, tokens: set[str]) -> bool:
    """Match a hint against text, using token-exact match for short hints to avoid
    false positives like 'c' matching 'science' or 'go' matching 'good'."""
    if len(hint) <= 3:
        return hint in tokens
    return hint in low


def _has_tech_signal(low: str, tokens: set[str]) -> bool:
    return any(_hint_matches(signal, low, tokens) for signal in TECH_SIGNAL_HINTS)


def _is_valid_jd_skill_candidate(skill: str) -> bool:
    cleaned = _normalize_ws(skill)
    if not cleaned:
        return False

    low = cleaned.lower()
    if any(h in low for h in NON_SKILL_PHRASE_HINTS):
        return False

    # Reject sentence-like requirements and long prose fragments.
    words = re.findall(r"[a-zA-Z0-9+#./&-]+", cleaned)
    if len(words) > 4 or len(cleaned) > 48:
        return False

    if any(p in cleaned for p in [";", ":", ".", "\n"]):
        return False

    tokens = _skill_tokens(cleaned)
    if _has_tech_signal(low, tokens):
        return True

    # Allow compact acronyms like OOP, SDLC, NLP when not caught above.
    compact = re.sub(r"[^A-Za-z]", "", cleaned)
    if compact.isupper() and 2 <= len(compact) <= 8:
        return True

    return False


def _is_skill_present(skill: str, present_keys: set[str]) -> bool:
    key = _normalize_skill_key(skill)
    if not key:
        return True
    if key in present_keys:
        return True
    tokens = [t for t in key.split() if len(t) > 2]
    if not tokens:
        return key in present_keys
    return any(all(t in existing for t in tokens) for existing in present_keys)


def _choose_skill_bucket(skill: str) -> str:
    low = skill.lower()
    tokens = _skill_tokens(skill)

    def hits(hints: set) -> bool:
        return any(_hint_matches(h, low, tokens) for h in hints)

    if hits(LANGUAGE_HINTS):
        return "Languages"
    if hits(FRAMEWORK_HINTS):
        return "Frameworks"
    if hits(DATABASE_HINTS):
        return "Databases"
    if hits(CLOUD_DEVOPS_HINTS):
        return "Cloud & DevOps"
    return "Specialized"


def _dedupe_skills_map(skills_map: dict[str, str]) -> dict[str, str]:
    deduped: dict[str, str] = {}
    seen: set[str] = set()
    for category, raw in skills_map.items():
        kept: list[str] = []
        for item in _split_csv_items(raw):
            key = _normalize_skill_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(item)
        if kept:
            deduped[category] = ", ".join(kept)
    return deduped


def _adjust_skills_for_jd(skills_map: dict[str, str], jd_analysis: dict) -> dict[str, str]:
    adjusted = {k: v for k, v in skills_map.items()}
    for cat in ["Languages", "Frameworks", "Databases", "Cloud & DevOps", "Specialized", "Soft Skills"]:
        adjusted.setdefault(cat, "")

    present = _build_skill_presence_set(adjusted)
    jd_skills = _dedupe(
        list(jd_analysis.get("must_have_skills", []))
        + list(jd_analysis.get("preferred_skills", []))
        + list(jd_analysis.get("ats_keywords", []))
    )

    for skill in jd_skills:
        cleaned = _normalize_ws(skill)
        if not _is_valid_jd_skill_candidate(cleaned):
            continue
        if not cleaned or _is_skill_present(cleaned, present):
            continue
        bucket = _choose_skill_bucket(cleaned)
        existing = _split_csv_items(adjusted.get(bucket, ""))
        existing.append(cleaned)
        adjusted[bucket] = ", ".join(existing)
        present.add(_normalize_skill_key(cleaned))

    return _dedupe_skills_map(adjusted)


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


def _normalize_key(value: str) -> str:
    return _normalize_ws(value).lower()


def _render_projects_for_prompt(projects: list[dict]) -> str:
    lines = []
    for proj in projects:
        lines.append(f"Project: {proj.get('full_name', proj.get('name', ''))}")
        lines.append(f"Tech Stack: {proj.get('tech_stack', '')}")
        for b in proj.get("bullets", []):
            lines.append(f"  - {b}")
        lines.append("")
    return "\n".join(lines)


def _render_experience_for_prompt(experience: list[tuple[str, list[str]]]) -> str:
    lines = []
    for company, bullets in experience:
        lines.append(f"Company: {company}")
        for b in bullets:
            lines.append(f"  - {b}")
        lines.append("")
    return "\n".join(lines)


def _rank_projects(
    all_projects: list[dict],
    jd_analysis: dict,
    n_slots: int,
    selected_project_names: list[str] | None = None,
) -> list[dict]:
    if not all_projects:
        return []

    jd_tokens = _build_jd_tokens(jd_analysis)
    selected = {_normalize_key(name) for name in (selected_project_names or [])}
    limit = max(1, n_slots * settings.PROJECT_CANDIDATE_MULTIPLIER)

    scored: list[tuple[int, int, dict]] = []
    for proj in all_projects:
        combined = " ".join([
            proj.get("name", ""),
            proj.get("tech_stack", ""),
            " ".join(proj.get("bullets", [])),
        ])
        score = _score_entry(combined, jd_tokens)
        proj_key = _normalize_key(proj.get("name", ""))
        is_selected = 1 if proj_key in selected else 0
        scored.append((is_selected, score, proj))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = [proj for _, _, proj in scored[:limit]]

    if selected:
        chosen_keys = {_normalize_key(p.get("name", "")) for p in top}
        for _, _, proj in scored:
            key = _normalize_key(proj.get("name", ""))
            if key in selected and key not in chosen_keys:
                top.append(proj)
                chosen_keys.add(key)

    return top


def _rank_experience(
    all_experience: dict[str, list[str]],
    jd_analysis: dict,
    selected_experience_companies: list[str] | None = None,
) -> list[tuple[str, list[str]]]:
    if not all_experience:
        return []

    jd_tokens = _build_jd_tokens(jd_analysis)
    selected = {_normalize_key(name) for name in (selected_experience_companies or [])}

    scored: list[tuple[int, int, str, list[str]]] = []
    for company, bullets in all_experience.items():
        key = _normalize_key(company)
        combined = company + " " + " ".join(bullets)
        score = _score_entry(combined, jd_tokens)
        is_selected = 1 if key in selected else 0
        scored.append((is_selected, score, company, bullets))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [(company, bullets) for _, _, company, bullets in scored]


def _merge_skills(current_skills: dict, ai_skills: dict, custom_skills: dict | None) -> dict:
    custom = custom_skills or {}
    current_presence = _build_skill_presence_set(current_skills)
    merged: dict[str, str] = {}

    for cat in ["Languages", "Frameworks", "Databases", "Cloud & DevOps", "Specialized", "Soft Skills"]:
        # 1. Explicit user edit always wins.
        if cat in custom and custom[cat]:
            merged[cat] = custom[cat]
            continue

        current_val = current_skills.get(cat, "")
        ai_val = ai_skills.get(cat, "")

        if ai_val and current_val:
            # Apply AI's reordering, but strip any item the AI hallucinated
            # (i.e. not present in the current resume).
            ai_items = _split_csv_items(ai_val)
            filtered = [item for item in ai_items if _is_skill_present(item, current_presence)]
            # Re-append anything the AI silently dropped (safety net).
            seen = {_normalize_skill_key(i) for i in filtered}
            for orig in _split_csv_items(current_val):
                if _normalize_skill_key(orig) not in seen:
                    filtered.append(orig)
            merged[cat] = ", ".join(filtered) if filtered else current_val
        else:
            # No AI value for this category — keep current as-is.
            merged[cat] = current_val

    # Preserve any non-standard categories the current resume has.
    for cat, val in current_skills.items():
        if cat not in merged:
            merged[cat] = val

    return _dedupe_skills_map(merged)


# ── Real ATS score: computed in Python after tailoring, never hallucinated ──

def _compute_ats_score(tailored_latex: str, ats_keywords: list[str]) -> dict:
    """
    Strip LaTeX commands, then deterministically check which ATS keywords
    from the JD appear in the resume text. Returns score 0-100.
    """
    plain = tailored_latex
    # Multiple passes unwrap nested commands like \textbf{\emph{Python}}
    for _ in range(4):
        plain = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^}]*)\}', r'\2', plain)
    plain = re.sub(r'\\[a-zA-Z]+\*?', ' ', plain)
    plain = re.sub(r'[{}]', ' ', plain)  # strip any remaining bare braces
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
    selected_project_names: list[str] | None = None,
    selected_experience_companies: list[str] | None = None,
    custom_skills: dict[str, str] | None = None,
) -> dict:
    current_summary = latex_utils.extract_summary(latex_resume)
    current_skills = latex_utils.extract_skills(latex_resume)
    current_projects = latex_utils.extract_projects(latex_resume)
    current_experience = latex_utils.extract_experience(latex_resume)
    current_experience_blocks = latex_utils.extract_experience_blocks(latex_resume)
    all_bank_projects = latex_utils.extract_projects(projects_bank)
    all_bank_experience_blocks = latex_utils.extract_experience_blocks(experience_bank)
    all_bank_experience = {entry["company"]: entry["bullets"] for entry in all_bank_experience_blocks}
    if not all_bank_experience:
        all_bank_experience = latex_utils.extract_experience(experience_bank)
    project_full_name_map = {
        _normalize_key(p.get("name", "")): p.get("full_name", p.get("name", ""))
        for p in all_bank_projects
    }

    n_slots = len(current_projects)

    # Pre-rank banks — LLM only sees the most relevant candidates
    ranked_projects = _rank_projects(
        all_projects=all_bank_projects,
        jd_analysis=jd_analysis,
        n_slots=n_slots,
        selected_project_names=selected_project_names,
    )
    ranked_experience = _rank_experience(
        all_experience=all_bank_experience,
        jd_analysis=jd_analysis,
        selected_experience_companies=selected_experience_companies,
    )
    if not ranked_projects:
        ranked_projects = current_projects
    if not ranked_experience:
        ranked_experience = list(current_experience.items())
    ranked_projects_bank = _render_projects_for_prompt(ranked_projects)
    ranked_experience_bank = _render_experience_for_prompt(ranked_experience)

    experience_bullet_cap = max(
        1, max((len(e.get("bullets", [])) for e in current_experience_blocks), default=1)
    )

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
            selected_project_names=selected_project_names,
            selected_experience_companies=selected_experience_companies,
            custom_skills=custom_skills,
            experience_bullet_cap=experience_bullet_cap,
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
        jd_analysis,
        current_experience,
        current_experience_blocks,
        all_bank_experience_blocks,
        project_full_name_map,
        selected_experience_companies,
        custom_skills,
    )

    issues = latex_guard.validate(updated_latex)
    if issues:
        result.setdefault("warnings", []).extend(issues)

    # Real ATS score — computed deterministically in Python, not by the model
    result["ats_score"] = _compute_ats_score(updated_latex, jd_analysis.get("ats_keywords", []))

    result["updated_latex"] = updated_latex
    return result


def apply_manual_edits(
    latex_resume: str,
    tailored_summary: str | None = None,
    tailored_skills: dict[str, str] | None = None,
    tailored_projects: list[dict] | None = None,
    tailored_experience: dict[str, list[str]] | None = None,
) -> dict:
    current_summary = latex_utils.extract_summary(latex_resume)
    current_skills = latex_utils.extract_skills(latex_resume)
    current_projects = latex_utils.extract_projects(latex_resume)
    current_experience = latex_utils.extract_experience(latex_resume)
    current_experience_blocks = latex_utils.extract_experience_blocks(latex_resume)

    project_full_name_map = {
        _normalize_key(p.get("name", "")): p.get("full_name", p.get("name", ""))
        for p in current_projects
    }

    result: dict = {
        "tailored_summary": tailored_summary if tailored_summary is not None else current_summary,
        "tailored_skills": tailored_skills or {},
        "tailored_projects": tailored_projects or current_projects,
        "tailored_experience": tailored_experience or current_experience,
    }

    updated_latex = _apply_changes(
        latex_resume,
        result,
        current_projects,
        current_summary,
        current_skills,
        {},
        current_experience,
        current_experience_blocks,
        current_experience_blocks,
        project_full_name_map,
        list((tailored_experience or {}).keys()),
        tailored_skills,
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
    jd_analysis: dict,
    current_experience: dict,
    current_experience_blocks: list[dict],
    all_bank_experience_blocks: list[dict],
    project_full_name_map: dict[str, str],
    selected_experience_companies: list[str] | None,
    custom_skills: dict[str, str] | None,
) -> str:
    project_bullet_cap = max(1, max((len(p.get("bullets", [])) for p in original_projects), default=1))
    experience_bullet_cap = max(1, max((len(e.get("bullets", [])) for e in current_experience_blocks), default=1))

    candidate_summary = result.get("tailored_summary") or ""
    subtle_summary = _choose_subtle_summary(current_summary, candidate_summary)
    subtle_summary = _trim_to_word_limit(subtle_summary or current_summary, MAX_SUMMARY_WORDS)
    if subtle_summary:
        result["tailored_summary"] = subtle_summary
        latex = latex_utils.replace_summary(latex, subtle_summary)
    else:
        result["tailored_summary"] = current_summary

    tailored_skills_payload = result.get("tailored_skills") if isinstance(result.get("tailored_skills"), dict) else {}
    if tailored_skills_payload or custom_skills:
        tailored_skills = _merge_skills(current_skills, tailored_skills_payload, custom_skills)
        tailored_soft = tailored_skills.get("Soft Skills", "")
        current_soft = current_skills.get("Soft Skills", "")
        tailored_skills["Soft Skills"] = _sanitize_soft_skills(tailored_soft, current_soft)
        result["tailored_skills"] = tailored_skills
        latex = latex_utils.replace_skills(latex, tailored_skills)

    slot_count = len(original_projects)
    cleaned_projects: list[dict] = []
    for proj in result.get("tailored_projects", []):
        name = _normalize_ws(proj.get("name", ""))
        if not name:
            continue
        cleaned_bullets = [_remove_obvious_targeting(b) for b in proj.get("bullets", [])]
        cleaned_bullets = [_trim_to_word_limit(b, MAX_BULLET_WORDS) for b in cleaned_bullets]
        cleaned_bullets = [b for b in cleaned_bullets if b]
        cleaned_bullets = cleaned_bullets[:project_bullet_cap]
        if not cleaned_bullets:
            continue

        cleaned_projects.append({
            "name": name,
            "full_name": project_full_name_map.get(_normalize_key(name), name),
            "tech_stack": proj.get("tech_stack", ""),
            "bullets": cleaned_bullets,
        })

    existing = {_normalize_key(p.get("name", "")) for p in cleaned_projects}
    for original in original_projects:
        if len(cleaned_projects) >= slot_count:
            break
        key = _normalize_key(original.get("name", ""))
        if key in existing:
            continue
        cleaned_projects.append({
            "name": original.get("name", ""),
            "full_name": original.get("full_name", original.get("name", "")),
            "tech_stack": original.get("tech_stack", ""),
            "bullets": original.get("bullets", []),
        })
        existing.add(key)

    if cleaned_projects:
        cleaned_projects = cleaned_projects[:slot_count] if slot_count > 0 else cleaned_projects
        result["tailored_projects"] = cleaned_projects
        latex = latex_utils.replace_projects_section(latex, cleaned_projects)

    experience_slot_count = len(current_experience_blocks)
    current_block_map = {
        _normalize_key(entry.get("company", "")): entry
        for entry in current_experience_blocks
        if entry.get("company")
    }
    bank_block_map = {
        _normalize_key(entry.get("company", "")): entry
        for entry in all_bank_experience_blocks
        if entry.get("company")
    }

    raw_experience = result.get("tailored_experience", {})
    ai_experience: dict[str, list[str]] = {}
    if isinstance(raw_experience, dict):
        for company, bullets in raw_experience.items():
            cleaned_bullets = [_remove_obvious_targeting(b) for b in (bullets or [])]
            cleaned_bullets = [_trim_to_word_limit(b, MAX_BULLET_WORDS) for b in cleaned_bullets]
            cleaned_bullets = [b for b in cleaned_bullets if b]
            cleaned_bullets = cleaned_bullets[:experience_bullet_cap]
            if cleaned_bullets:
                ai_experience[_normalize_key(company)] = cleaned_bullets

    ordered_keys: list[str] = []
    seen_keys: set[str] = set()

    for company in (selected_experience_companies or []):
        key = _normalize_key(company)
        if key and key not in seen_keys:
            ordered_keys.append(key)
            seen_keys.add(key)

    for key in ai_experience.keys():
        if key not in seen_keys:
            ordered_keys.append(key)
            seen_keys.add(key)

    chosen_entries: list[dict] = []
    used_keys: set[str] = set()

    for key in ordered_keys:
        base_entry = bank_block_map.get(key) or current_block_map.get(key)
        if not base_entry:
            continue
        chosen_entries.append({
            "company": base_entry.get("company", ""),
            "header": base_entry.get("header", ""),
            "bullets": [
                _trim_to_word_limit(b, MAX_BULLET_WORDS)
                for b in ai_experience.get(key, base_entry.get("bullets", []))[:experience_bullet_cap]
            ],
        })
        used_keys.add(key)
        if experience_slot_count and len(chosen_entries) >= experience_slot_count:
            break

    for entry in current_experience_blocks:
        key = _normalize_key(entry.get("company", ""))
        if not key or key in used_keys:
            continue
        chosen_entries.append({
            "company": entry.get("company", ""),
            "header": entry.get("header", ""),
            "bullets": [
                _trim_to_word_limit(b, MAX_BULLET_WORDS)
                for b in ai_experience.get(key, entry.get("bullets", []))[:experience_bullet_cap]
            ],
        })
        used_keys.add(key)
        if experience_slot_count and len(chosen_entries) >= experience_slot_count:
            break

    if chosen_entries:
        if experience_slot_count > 0:
            chosen_entries = chosen_entries[:experience_slot_count]
        result["tailored_experience"] = {
            entry.get("company", ""): entry.get("bullets", [])
            for entry in chosen_entries
            if entry.get("company")
        }
        latex = latex_utils.replace_experience_section(latex, chosen_entries)

    return latex
