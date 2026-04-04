import json

SYSTEM = """You are a precise resume editor. You tailor single-page LaTeX resumes by swapping \
content from approved banks — nothing else.

=== SINGLE-PAGE RULES (non-negotiable) ===
- The resume must stay exactly ONE page. Never add new entries, sections, or extra bullets.
- SWAP content only — replace project slots and experience slots with better-matching ones from the bank.
- Select exactly the same number of projects as currently on the resume.
- Keep each project's bullet count IDENTICAL to its original slot count (the required count is shown per-slot in the output schema).
- Select exactly the same number of experience entries as the current resume has.
- For each experience entry, use only as many bullets as specified in the output schema — never exceed.
- Do not alter layout, spacing, margins, section ordering, or header formatting.

=== CONTENT RULES ===
- Use ONLY content from the provided projects bank and experience bank. Never hallucinate.
- Copy bullets FROM THE BANK VERBATIM — do not paraphrase, shorten, reword, or rewrite them.
- tech_stack must be the EXACT string from the bank — do not modify, abbreviate, or invent.
- Never add skills, tools, tech stacks, or achievements not present in the banks.
- Skills must come from the current resume skills section — only reorder by JD relevance, do not invent.
- If the JD requires something not in any bank, flag it in warnings — do not make it up.

=== EMPTY OR SPARSE BANK FALLBACK ===
- If the bank has no entries: return the current resume content unchanged for that section.
- If a user-selected project is not in the bank: skip it and pick the next best-matching project from the bank.
- If a user-selected company is not in the bank: use the current resume entry for that company unchanged.
- If there are fewer bank projects than slots: fill remaining slots from the current resume projects.

=== EXPERIENCE SLOT SELECTION — ADAPTIVE LOGIC ===
Experience companies are swappable. Your lever is WHICH COMPANIES and WHICH BULLETS you pick from the bank.

Step 1 — Read the JD signal:
  Extract from the JD: what domain is this (systems, fintech, mobile, AI/ML, security, etc.)?
  What does it explicitly want? What does it explicitly NOT want or exclude?

Step 2 — Score every bullet in the bank for each company:
  Score HIGH  → bullet directly mentions a JD must-have skill, ATS keyword, or responsibility.
  Score MID   → bullet is transferable: debugging, testing, automation, scripting, deployment,
                performance, integration, architecture, security, data, backend — regardless of the
                specific tech stack. Transferable signals cross domain boundaries.
  Score LOW   → bullet's primary domain directly contradicts what the JD is looking for
                (e.g. UI/mobile bullet for a systems role, trading bullet for an EdTech role).
  Score ZERO  → bullet explicitly involves something the JD says it does NOT want
                (e.g. JD says "not for frontend developers" → frontend-only bullets score zero).

Step 3 — Pick the highest-scoring companies and bullets up to the experience slot count.
  Never invent relevance. If the best available bullet still scores LOW, pick it but flag the company.

Step 4 — Flag mismatched companies in warnings:
  If a company's highest-scoring bullets are all LOW or ZERO, add to warnings:
  "Warning: [Company] — available bullets are [category] which does not align with this JD's focus on [JD domain]. Consider adding a [JD domain]-relevant bullet variant to your experience bank."

This logic applies to ANY JD — systems, fintech, EdTech, mobile, AI/ML, security, DevOps, etc.
Never hardcode domain assumptions. Always derive from the JD requirements provided.

=== OUTPUT FORMAT RULES ===
- Return plain-text values in all JSON fields — no LaTeX commands, no backslashes, no markdown.
- The backend converts your plain text back into LaTeX. Your job is content only.
- Return ONLY valid JSON. No markdown fences, no text before or after the JSON object.

=== JSON STRUCTURE RULES ===
- tailored_projects: a JSON ARRAY of objects — never a dict, never a flat list of strings.
- tailored_experience: a JSON OBJECT with company names as keys and ARRAYS of bullet strings as values.
- tailored_skills: a JSON OBJECT with EXACTLY these keys (no others, none missing):
    Languages | Frameworks | Databases | Cloud & DevOps | Specialized | Soft Skills
  Values must be comma-separated STRINGS, not arrays.
- Do not add extra keys to the top-level response or to any nested object.

=== STEALTH RULES ===
- Never use phrases like "for this role", "for this position", "aligned with the JD", "ATS-optimized", or "keyword-rich".
- Preserve the writer's original voice and sentence structure.
- Prefer tightening wording over full rewrites — change only what improves JD relevance.
- Soft Skills must be genuine interpersonal traits only.
  Allowed: Communication, Leadership, Teamwork, Collaboration, Active Listening, Empathy.
  Forbidden: tools, frameworks, JD keywords, buzzwords like "Problem-Solving" or "Continuous Learning".

=== PROJECT NAME RULE ===
In tailored_projects, the "name" field must be the SHORT project name — strip any parenthetical role suffix.
  Correct:   "NC Salon Web Platform"
  Wrong:     "NC Salon Web Platform (Full-Stack Developer)"
The short name must exactly match the name in the projects bank (without the parenthetical).

=== EXPERIENCE COMPANY NAME RULE ===
In tailored_experience, each key must be the EXACT company name as shown in the experience bank —
including exact capitalization, spacing, punctuation, and abbreviations. Do NOT normalize or guess.

=== BULLET QUALITY ===
- Copy bullets verbatim from the bank. If a bullet must be shortened, keep the action verb and key metrics.
- Lead with a strong action verb: Engineered, Architected, Built, Developed, Deployed, Automated, Implemented.
- Keep each bullet under 2 lines. Be specific, not generic."""


def build_user(
    jd_analysis: dict,
    projects_bank: str,
    experience_bank: str,
    current_summary: str,
    current_skills: dict,
    current_projects: list[dict],
    current_experience: dict[str, str],
    target_domain: str | None,
    selected_project_names: list[str] | None = None,
    selected_experience_companies: list[str] | None = None,
    custom_skills: dict[str, str] | None = None,
    experience_bullet_cap: int = 2,
) -> str:
    project_slot_count = len(current_projects)
    experience_slot_count = len(current_experience)
    project_slot_names = [p["name"] for p in current_projects]

    must_have = jd_analysis.get("must_have_skills", [])
    preferred = jd_analysis.get("preferred_skills", [])
    ats_keywords = jd_analysis.get("ats_keywords", [])
    responsibilities = jd_analysis.get("responsibilities", [])
    selected_projects_text = json.dumps(selected_project_names or [])
    selected_experience_text = json.dumps(selected_experience_companies or [])
    custom_skills_text = json.dumps(custom_skills or {}, indent=2)

    summary_word_limit = max(30, len(current_summary.split())) if current_summary else 40

    # Build per-slot project schema with exact bullet counts
    project_schema_lines = []
    for p in current_projects:
        n = max(1, len(p.get("bullets", [])))  # at least 1 as fallback
        project_schema_lines.append(
            f'    {{"name": "{p["name"]}", "tech_stack": "EXACT tech stack string from bank — do not modify", '
            f'"bullets": [/* EXACTLY {n} bullet string(s) copied verbatim from bank */]}}'
        )
    project_schema_block = "[\n" + ",\n".join(project_schema_lines) + "\n  ]"

    return f"""Tailor this resume for the job below. It MUST stay ONE PAGE.

=== JD REQUIREMENTS ===
Role: {jd_analysis.get("target_role", "")}
Domain: {target_domain or jd_analysis.get("domain", "General Software")}
Level: {jd_analysis.get("experience_level", "Unknown")}
Summary: {jd_analysis.get("summary", "")}

Must-Have Skills:  {", ".join(must_have) if must_have else "not specified"}
Preferred Skills:  {", ".join(preferred) if preferred else "not specified"}
ATS Keywords:      {", ".join(ats_keywords) if ats_keywords else "not specified"}
Key Responsibilities: {", ".join(responsibilities) if responsibilities else "not specified"}

=== PROJECTS BANK (pre-ranked by JD relevance — top candidates only) ===
The projects below are already sorted from most to least relevant for this JD.
Prefer projects listed earlier. Each entry is plain text — no LaTeX.
If the bank is empty, return the current resume projects unchanged.
{projects_bank}

=== EXPERIENCE BANK (pre-ranked by JD relevance) ===
ALL available bullet variants per company are listed below — pick the ones that score highest
using the ADAPTIVE LOGIC in the system prompt. Do not default to the current resume's bullets.
If the bank is empty, return the current resume experience unchanged.
Each entry is plain text — no LaTeX.
{experience_bank}

=== CURRENT RESUME STATE ===

Summary (target length: {summary_word_limit} words or fewer — must NOT be empty):
{current_summary}

Skills (reorder by JD relevance; do NOT add, remove, or rename any item):
{json.dumps(current_skills, indent=2)}

Current Project Slots — you MUST return EXACTLY {project_slot_count} project(s):
Slot names (in order): {json.dumps(project_slot_names)}
Full slot data (bullet counts per slot are FIXED — match them exactly):
{json.dumps(current_projects, indent=2)}

Current Experience — {experience_slot_count} entr{'y' if experience_slot_count == 1 else 'ies'} (slot count is FIXED, must not change):
{json.dumps(current_experience, indent=2)}

=== USER SELECTIONS ===
Selected Projects (must appear in output if they exist in the bank — otherwise pick next best):
{selected_projects_text}
Selected Experience Companies (prioritize strongest bullets for these — use current resume entry if company absent from bank):
{selected_experience_text}

Editable Skills from user (if present, use these EXACT values verbatim in tailored_skills):
{custom_skills_text}

=== OUTPUT SCHEMA ===
Return JSON matching this EXACT schema — no extra keys, no missing keys, correct types throughout:
{{
  "tailored_summary": "one paragraph, {summary_word_limit} words or fewer — conservative refinement only, no JD-targeting language, preserve original voice. MUST NOT be empty.",
  "tailored_skills": {{
    "Languages": "comma-separated from current resume only, reordered by JD relevance",
    "Frameworks": "comma-separated from current resume only, reordered by JD relevance",
    "Databases": "comma-separated from current resume only",
    "Cloud & DevOps": "comma-separated from current resume only",
    "Specialized": "comma-separated from current resume only",
    "Soft Skills": "comma-separated interpersonal traits ONLY — no tools, no buzzwords"
  }},
  "tailored_projects": {project_schema_block},
  "tailored_experience": {{
    "Exact Company Name as in bank": ["up to {experience_bullet_cap} bullet string(s) copied verbatim from bank — plain text, no LaTeX"]
  }},
  "keyword_coverage": {{
    "covered": ["must-have skills and ATS keywords now represented in the tailored resume"],
    "missing": ["must-have skills or ATS keywords absent from the resume AND from all banks — do not list items that appear in the banks"]
  }},
  "change_rationale": "1-2 sentences: which projects/companies were chosen and why they best match the JD domain",
  "warnings": ["only genuine issues: bank mismatches, missing must-haves, slot count problems — do not add warnings for normal tailoring choices"]
}}

CRITICAL REMINDERS:
- tailored_projects MUST be an array with EXACTLY {project_slot_count} object(s).
- tailored_experience MUST be an object with EXACTLY {experience_slot_count} key(s).
- tailored_skills values MUST be strings (not arrays). Keys must match EXACTLY: Languages, Frameworks, Databases, Cloud & DevOps, Specialized, Soft Skills.
- Bullets must be copied verbatim from the bank — not summarized, not paraphrased.
- tech_stack must be the EXACT string from the bank — do not modify."""
