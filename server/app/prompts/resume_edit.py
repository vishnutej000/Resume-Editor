import json

SYSTEM = """You are a precise resume editor. You tailor single-page LaTeX resumes by swapping \
content from approved banks — nothing else.

=== SINGLE-PAGE RULES (non-negotiable) ===
- The resume must stay exactly ONE page. Never add new entries, sections, or extra bullets.
- SWAP content only — replace project slots and experience bullets with better-matching ones from the bank.
- Select exactly the same number of projects as currently on the resume.
- Keep each project's bullet count IDENTICAL to its original slot count.
- For experience, match or reduce bullet count — never exceed the original.

=== CONTENT RULES ===
- Use ONLY content from the provided projects bank and experience bank. Never hallucinate.
- Never add skills, tools, tech stacks, or achievements not present in the banks.
- Skills must come from the current resume skills section — only reorder by JD relevance, do not invent.
- If the JD requires something not in any bank, flag it in warnings — do not make it up.

=== OUTPUT FORMAT RULES ===
- Return plain-text values in all JSON fields — no LaTeX commands, no backslashes, no markdown.
- The backend converts your plain text back into LaTeX. Your job is content only.
- Return ONLY valid JSON. No markdown fences, no text before or after the JSON object.

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
In tailored_experience, each key must be the exact company name from the current resume — character-for-character, including spacing and punctuation.

=== BULLET QUALITY ===
- Lead with a strong action verb: Engineered, Architected, Built, Developed, Deployed, Automated, Implemented.
- Include technology names and scale/impact details where the bank supplies them.
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
) -> str:
    project_slot_count = len(current_projects)
    experience_slot_count = len(current_experience)
    project_slot_names = [p["name"] for p in current_projects]

    must_have = jd_analysis.get("must_have_skills", [])
    preferred = jd_analysis.get("preferred_skills", [])
    ats_keywords = jd_analysis.get("ats_keywords", [])

    return f"""Tailor this resume for the job below. It MUST stay ONE PAGE.

=== JD REQUIREMENTS ===
Role: {jd_analysis.get("target_role", "")}
Domain: {target_domain or jd_analysis.get("domain", "General Software")}
Level: {jd_analysis.get("experience_level", "Unknown")}

Must-Have Skills:  {", ".join(must_have) if must_have else "not specified"}
Preferred Skills:  {", ".join(preferred) if preferred else "not specified"}
ATS Keywords:      {", ".join(ats_keywords) if ats_keywords else "not specified"}

=== PROJECTS BANK (all available projects to choose from) ===
{projects_bank}

=== EXPERIENCE BANK ===
{experience_bank}

=== CURRENT RESUME STATE ===

Summary:
{current_summary}

Skills:
{json.dumps(current_skills, indent=2)}

Current Project Slots — you MUST return exactly {project_slot_count} projects:
Slot names (in order): {json.dumps(project_slot_names)}
Full slot data:
{json.dumps(current_projects, indent=2)}

Current Experience — {experience_slot_count} entries, preserve all companies:
{json.dumps(current_experience, indent=2)}

=== OUTPUT SCHEMA ===
Return JSON matching this exact schema (no extra keys, no missing keys):
{{
  "tailored_summary": "one paragraph — conservative refinement of current summary, same length or shorter, no JD-targeting language",
  "tailored_skills": {{
    "Languages": "comma-separated from current resume, reordered by JD relevance",
    "Frameworks": "comma-separated from current resume, reordered by JD relevance",
    "Databases": "comma-separated from current resume",
    "Cloud & DevOps": "comma-separated from current resume",
    "Specialized": "comma-separated from current resume",
    "Soft Skills": "comma-separated interpersonal traits only"
  }},
  "tailored_projects": [
    {{
      "name": "SHORT project name — no parenthetical suffix",
      "tech_stack": "exact tech stack string from the bank",
      "bullets": ["same number of bullets as the original slot — plain text, no LaTeX"]
    }}
  ],
  "tailored_experience": {{
    "Exact Company Name": ["same bullet count as original — plain text, no LaTeX"]
  }},
  "keyword_coverage": {{
    "covered": ["which must-have skills and ATS keywords are now represented in the tailored resume"],
    "missing": ["which must-have skills or ATS keywords are absent from the resume AND from all banks"]
  }},
  "change_rationale": "1-2 sentences: which projects were swapped and why they better match the JD",
  "warnings": ["any must-have JD requirement that cannot be addressed from the available banks"]
}}"""
