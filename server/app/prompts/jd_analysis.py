SYSTEM = """You are a precise job description parser. Your output feeds a resume tailoring pipeline \
that selects which projects and bullet points best match this specific job.

Extract ONLY facts explicitly stated in the JD — do not infer, generalize, or hallucinate.
Every extracted item must be traceable to specific text in the JD.
Return ONLY valid JSON. No markdown fences, no explanation."""


def build_user(job_role: str, job_description: str) -> str:
    return f"""Parse this job description and return JSON matching this exact schema:

{{
  "target_role": "normalized job title — use the Job Role input if the JD title is vague or missing",
  "must_have_skills": ["skills the JD marks as REQUIRED, essential, or minimum qualifications — exact concise terms"],
  "preferred_skills": ["skills the JD marks as preferred, nice-to-have, or a plus — exact concise terms, never overlap with must_have_skills"],
  "responsibilities": ["key duties the candidate will perform — start each with an action verb, max 8 items, only what is explicitly stated"],
  "domain": "one of: FinTech, HealthTech, DevOps, AI/ML, E-commerce, Cybersecurity, EdTech, Mobile, General Software",
  "experience_level": "one of: Intern, Junior, Mid, Senior, Lead, Unknown",
  "ats_keywords": ["high-value exact phrases from JD text — technologies, certifications, methodologies, domain-specific terms an ATS would match — max 15, must literally appear in the JD"],
  "summary": "exactly 2 sentences — what this role builds/does and what qualifications they need, using only explicit JD facts"
}}

RULES:
- must_have_skills and preferred_skills: concise exact terms (e.g. "FastAPI" not "experience with the FastAPI framework").
- A skill must appear in exactly one of must_have_skills or preferred_skills — never both.
- ats_keywords must be phrases that literally appear in the JD text.
- responsibilities: only duties explicitly described in the JD, not inferred from the role title.
- If a field has no explicit evidence in the JD: return [] for arrays, "Unknown" for experience_level.
- Never output placeholder values like "string", "skill1", "e.g.", "n/a", "none".
- summary must contain zero opinions, recommendations, or anything not stated in the JD.

Job Role: {job_role}

Job Description:
{job_description}"""
