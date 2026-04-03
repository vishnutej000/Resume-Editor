import re

from app.core.ai_client import call_ai, parse_json
from app.prompts import jd_analysis as prompt


ALLOWED_DOMAINS = ["FinTech", "HealthTech", "DevOps", "AI/ML", "E-commerce", "General Software"]
EXPERIENCE_LEVELS = {"junior", "mid", "senior", "lead", "unknown"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        cleaned = _normalize(item)
        low = cleaned.lower()
        if not cleaned or low in seen:
            continue
        seen.add(low)
        out.append(cleaned)
    return out


def _is_placeholder(text: str) -> bool:
    low = _normalize(text).lower()
    return low in {"string", "unknown string", "n/a", "na", "none", ""} or "e.g." in low


def _supported_by_jd(phrase: str, jd_text: str) -> bool:
    jd = jd_text.lower()
    cleaned = re.sub(r"[^a-z0-9\s/+\-.]", "", phrase.lower()).strip()
    if not cleaned:
        return False
    if cleaned in jd:
        return True
    tokens = [t for t in re.split(r"[\s/+\-.]+", cleaned) if len(t) > 2]
    if not tokens:
        return False
    overlap = sum(1 for t in tokens if t in jd)
    return overlap >= max(1, int(len(tokens) * 0.6))


def _ground_list(values: list[str], jd_text: str) -> list[str]:
    cleaned = _dedupe([v for v in values if not _is_placeholder(v)])
    return [v for v in cleaned if _supported_by_jd(v, jd_text)]


def _infer_domain(jd_text: str) -> str:
    jd = jd_text.lower()
    rules = [
        ("HealthTech", ["pharma", "biotech", "healthcare", "medical", "clinical", "patient"]),
        ("FinTech", ["fintech", "bank", "banking", "payment", "trading", "finance"]),
        ("AI/ML", ["machine learning", "ml", "ai", "llm", "nlp", "deep learning"]),
        ("DevOps", ["devops", "sre", "kubernetes", "docker", "ci/cd", "terraform", "infrastructure"]),
        ("E-commerce", ["e-commerce", "ecommerce", "cart", "checkout", "marketplace"]),
    ]
    for domain, hints in rules:
        if any(h in jd for h in hints):
            return domain
    return "General Software"


def _infer_experience_level(jd_text: str) -> str:
    jd = jd_text.lower()
    if any(k in jd for k in ["lead", "principal", "staff engineer"]):
        return "Lead"
    if any(k in jd for k in ["senior", "5+ years", "6+ years", "7+ years"]):
        return "Senior"
    if any(k in jd for k in ["junior", "entry level", "intern", "0-2 years", "1-2 years"]):
        return "Junior"
    if any(k in jd for k in ["3+ years", "2+ years", "mid-level", "mid level"]):
        return "Mid"
    return "Unknown"


def _extract_signal_phrases(jd_text: str) -> list[str]:
    jd = jd_text.lower()
    candidates = [
        "pharma engineering",
        "apprenticeship program",
        "engineering graduates",
        "training program",
        "production systems",
        "fastapi",
        "rest apis",
        "docker",
        "sql",
        "microservices",
        "teamwork",
        "communication",
    ]
    found = [phrase for phrase in candidates if phrase in jd]
    return _dedupe([p.title() if p.islower() else p for p in found])


def _fallback_summary(job_role: str, must: list[str], preferred: list[str], jd_text: str) -> str:
    role = _normalize(job_role) or "the role"
    must_txt = ", ".join(must[:4]) if must else "relevant technical skills"
    pref_txt = ", ".join(preferred[:3]) if preferred else "collaboration and execution"
    return (
        f"The JD is hiring for {role}. It emphasizes {must_txt}. "
        f"Preferred areas include {pref_txt}."
    )


def _normalize_analysis(raw: dict, job_role: str, job_description: str) -> dict:
    jd_text = job_description or ""
    target_role = _normalize(raw.get("target_role") or job_role)
    if _is_placeholder(target_role):
        target_role = _normalize(job_role)

    must_have = _ground_list(raw.get("must_have_skills", []), jd_text)
    preferred = _ground_list(raw.get("preferred_skills", []), jd_text)
    responsibilities = _ground_list(raw.get("responsibilities", []), jd_text)

    domain = _normalize(raw.get("domain", ""))
    if domain not in ALLOWED_DOMAINS:
        domain = _infer_domain(jd_text)
    elif domain == "General Software":
        inferred = _infer_domain(jd_text)
        if inferred != "General Software":
            domain = inferred

    level = _normalize(raw.get("experience_level", "Unknown")).title()
    if level.lower() not in EXPERIENCE_LEVELS:
        level = _infer_experience_level(jd_text)

    ats_keywords = _ground_list(raw.get("ats_keywords", []), jd_text)
    if not ats_keywords:
        ats_keywords = _dedupe(must_have + preferred + _extract_signal_phrases(jd_text))[:10]

    summary = _normalize(raw.get("summary", ""))
    if _is_placeholder(summary) or len(summary.split()) < 12:
        summary = _fallback_summary(target_role or job_role, must_have, preferred, jd_text)

    return {
        "target_role": target_role or _normalize(job_role),
        "must_have_skills": must_have,
        "preferred_skills": preferred,
        "responsibilities": responsibilities,
        "domain": domain,
        "experience_level": level,
        "ats_keywords": ats_keywords,
        "summary": summary,
    }


async def analyze(job_role: str, job_description: str) -> dict:
    messages = [
        {"role": "system", "content": prompt.SYSTEM},
        {"role": "user", "content": prompt.build_user(job_role, job_description)},
    ]
    raw = await call_ai(messages, json_mode=True, temperature=0.0)
    parsed = parse_json(raw)
    return _normalize_analysis(parsed, job_role, job_description)
