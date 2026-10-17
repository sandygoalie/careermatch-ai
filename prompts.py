"""All prompt text in one place."""

BASE_RULES = """You are CareerMatch AI, an expert career coach and recruiter helping a candidate prepare for a specific role. You provide career guidance and decision support, never hiring decisions.

Ground rules:
- Base every candidate-specific statement only on the supplied CV. Never invent qualifications, employers, dates, titles, achievements, projects or numbers.
- Where a strong answer needs information the CV doesn't contain, write [NEEDS INPUT: <what is needed>] instead of guessing.
- Credit transferable skills where the CV evidence supports them, and say briefly why the skill transfers.
- The candidate's personal details have been replaced with placeholders such as [CANDIDATE], [EMAIL], [PHONE]. Keep the placeholders as they are.
- Never consider age, gender, marital status, religion, caste, nationality, disability or other protected characteristics.
- Quote CV evidence verbatim (short excerpts) when asked for evidence.
- Be specific to this JD and this CV; avoid generic advice."""

JD_EXTRACT = """Extract the structured content of this job description.

- company: the hiring company's name, or "" if it isn't stated{company_hint}.
- role_type: "consulting" for management/strategy/tech/operations consulting roles (including Big 4 advisory); otherwise the closest fit.
- skills: every distinct skill, tagged technical/soft/domain; must_have is true only when the JD marks it required (or it is clearly essential to the core role).
- keywords: 15-30 terms an ATS would screen for (skills, tools, methods, domain terms, qualifications). Give each 0-4 common synonyms or abbreviations (e.g. "supply chain management" -> ["SCM"]) and an importance level.
- Use "" or [] for anything not stated.

<job_description>
{jd}
</job_description>"""

CV_EXTRACT = """Extract the structured content of this CV.

- contact: the candidate's name, emails, phones, location/address and profile links exactly as written (used only for privacy redaction).
- experience: one entry per role, bullets verbatim.
- measurable_results: every quantified outcome, each with the exact source_quote it came from.
- total_years_experience: your estimate from the dates (e.g. "about 4 years"), or "unclear".
- Use "" or [] for anything not present. Do not infer or add anything.

<cv>
{cv}
</cv>"""

CONTEXT = """<job_description_structured>
{jd_json}
</job_description_structured>

<cv_text>
{cv}
</cv_text>"""

FIT = """Assess how well this CV fits the JD.

1. dimensions: score each of the 8 dimensions (experience, responsibilities, skills, technical, education, industry, leadership, soft_skills) from 0 to 10 against what THIS JD needs. 10 = fully meets or exceeds, 5 = partially, 0 = no evidence. Give a 2-3 sentence rationale and short verbatim CV evidence quotes. Do not compute an overall total.
2. requirements: one row per distinct JD requirement (responsibilities, qualifications, must-have skills, experience level, important tools). status strong/partial/gap; cv_evidence a verbatim quote or "" for gaps; transferable_note when a partial or strong match relies on transferable experience; claim_type "fact" when directly evidenced, "assumption" when inferred.
3. summary: 3-4 sentences, balanced. Do not express fit as a probability of being hired.

{context}"""

STRENGTHS_GAPS = """Using the fit analysis below, identify:

- strengths: exactly 5 top strengths for this role, each with a verbatim CV evidence quote and the JD requirement it serves.
- gaps: all meaningful gaps. severity "critical" = an unmet must-have; "moderate" = a partially met or important requirement; "minor" = nice-to-have. For each: why it matters for this role, how to close it short-term (before the interview) and long-term, how to frame it honestly in an interview, and 1-3 learning resources. Only name well-known resources (official documentation, named courses or certifications); give an official URL only if you are certain it exists, otherwise a search phrase.

<fit_analysis>
{fit_json}
</fit_analysis>

{context}"""

CV_OPTIMIZE = """Optimise this CV for the JD and applicant tracking systems.

- missing_keywords: for each of these keywords not found in the CV: {missing}. Use "add_if_true" when the CV suggests the candidate may have it but didn't say so (note where it could go), else "genuine_gap".
- weak_statements: the 5-10 weakest or vaguest CV bullets: original text verbatim, what's weak, and a stronger rewrite that leads with action and impact and uses JD language where truthful. Use only facts in the CV. If a metric would help but isn't in the CV, put [NEEDS INPUT: e.g. % cost reduced] in the rewrite.
- tailored_cv_markdown: a complete ATS-friendly CV in Markdown (single column; standard headings: Summary, Experience, Education, Skills, then Projects/Certifications if present). Keep [CANDIDATE], [EMAIL], [PHONE], [LINK] placeholders in the header. Reorder and rephrase to match the JD, but never add employers, roles, dates, qualifications, skills or numbers that aren't in the CV. Mark every spot needing the candidate's input with [NEEDS INPUT: ...].
- change_notes: the key changes you made and why.

{context}"""

RESEARCH_COMPANY = """Research the company "{company}" for a candidate interviewing for the role "{role}". Today's date is {today}.

Use web search. Cover: company overview and business model; major products, services and markets; main competitors; strategy and growth priorities; recent announcements, deals and developments (prefer the last 12 months); and relevant recent articles or reports.

Rules:
- Every verified fact must come from a page you actually retrieved in this search session. Put that page's exact URL in source_url. Never invent or guess a URL, title or date.
- published_date: the publication date as stated by the source (YYYY-MM-DD or "Month YYYY"), or "" if unknown.
- Keep facts (cited) separate from your analysis and from interview recommendations.
- If you cannot confidently identify the company, set identified to false and explain in notes.

Finish your answer with ONLY a JSON object in a ```json code block, in this shape:
{{"subject": str, "identified": bool,
  "verified_facts": [{{"topic": "overview|business_model|products_markets|competitors|strategy|recent_developments|articles", "statement": str, "source_url": str, "source_title": str, "published_date": str}}],
  "analysis": [str], "interview_implications": [str], "notes": str}}
Aim for 12-20 verified facts."""

RESEARCH_INDUSTRY = """Research the industry "{industry}" (context: a {role} role{company_clause}). Today's date is {today}.

Use web search. Cover: key industry trends; challenges; relevant regulations and policy changes; technology shifts (e.g. AI, automation, digitisation) and their effect on this kind of role; and notable recent reports or articles.

Rules:
- Every verified fact must come from a page you actually retrieved in this search session. Put that page's exact URL in source_url. Never invent or guess a URL, title or date.
- published_date: as stated by the source, or "" if unknown.
- Keep facts (cited) separate from analysis and interview recommendations.

Finish your answer with ONLY a JSON object in a ```json code block, in this shape:
{{"subject": str, "identified": true,
  "verified_facts": [{{"topic": "trends|challenges|regulation|technology|reports", "statement": str, "source_url": str, "source_title": str, "published_date": str}}],
  "analysis": [str], "interview_implications": [str], "notes": str}}
Aim for 10-16 verified facts."""

QUESTIONS = """Create a personalised mock interview questionnaire for this candidate and role.

- questions: at least 32 questions in total, at least 5 per category: hr_behavioral, cv_based (probe specific CV entries), jd_based, company, technical (role-relevant technical/functional knowledge), follow_up (difficult probing follow-ups on weak spots or gaps).
- For each: what the interviewer is evaluating; answer_guidance (a suggested answer outline or framework that draws on the candidate's real CV content, with [NEEDS INPUT] where the CV lacks material); common pitfalls; priority high/medium/low. Mark about 10 as high priority: the questions this candidate is most likely to face or most at risk on.
- feedback_guidance: 6-10 points the candidate can use to self-assess recorded practice answers (structure, specificity, evidence, length, etc.).

Known gaps and risks to probe:
{gaps}

Company research summary (use for company questions; don't add new facts):
{research}

{context}"""

CASES = """The role is a consulting role. Create case interview practice material tailored to the industry ({industry}) and the company context where possible.

Provide exactly one case for each case_type: profitability, market_entry, growth_strategy, pricing, operations, market_sizing, business_problem (an unstructured business problem).
For each: a realistic case prompt as an interviewer would say it; 3-5 good clarifying questions; an issue-tree framework (3-5 branches with sub-points); key assumptions/numbers the candidate could use (clearly marked as illustrative); a model answer outline (6-10 steps through to a recommendation); and a rubric covering structure, maths, insight and communication.

{context}"""

COACHING = """Create personalised coaching material.

- answers: tailored answers for exactly these four: "Tell me about yourself", "Why this company?", "Why this role?", "Why should we hire you?". Use only real CV content; for "Why this company?" use only the research summary below. Each answer 120-220 words, natural spoken style, with [NEEDS INPUT] where personal motivation is needed. tips: how to deliver it.
- stories: a STAR story for each theme: leadership, teamwork, conflict, failure, problem_solving, initiative, achievement. Each must be built from a specific CV entry (name it in cv_source) and set backed_by_cv true. Use only facts from the CV; put [NEEDS INPUT: ...] for details the candidate must supply (often the conflict, failure and exact results). If the CV has nothing usable for a theme, set backed_by_cv false, cv_source "", and write prompts telling the candidate what kind of experience to recall instead of inventing one.
- red_flags: potential concerns an interviewer may notice in this CV against this JD (date gaps, short tenures, career switches, missing must-haves, level mismatch). For each, an honest way to address it. Return [] if there are none.

Company research summary:
{research}

Known gaps:
{gaps}

{context}"""

PLAN = """Create a 7-day interview preparation plan for this candidate.

- days: Day 1-7. Prioritise critical gaps first, then high-priority questions, STAR stories and company knowledge; Day 7 is a full mock-interview run and revision. Each day: a focus, 3-5 concrete tasks, practice items (name specific questions or cases from the materials below), 1-3 learning resources (well-known only; search phrase unless certain of the URL), a time estimate, and the revision focus.
- top_actions: the 3 most effective actions to become more competitive for this role, each with a rationale.
- competitive_advantages: 3-5 things that differentiate this candidate for this role, based on CV evidence.
- interview_risks: the 3-5 biggest risks in the interview.
- top_priorities: the top 3 preparation priorities, one line each.

<strengths_and_gaps>
{sg_json}
</strengths_and_gaps>

<high_priority_questions>
{questions}
</high_priority_questions>

<red_flags>
{red_flags}
</red_flags>

Case practice available: {has_cases}

{context}"""
