"""Pydantic models for every pipeline stage output.

These double as JSON schemas for Claude's structured outputs, so keep them free of
numeric/length constraints (validated in code where needed instead).
"""

from typing import List, Literal

from pydantic import BaseModel

ClaimType = Literal["fact", "assumption", "recommendation"]
Importance = Literal["must_have", "important", "nice_to_have"]


# ---------- Stage 1: JD extraction ----------

class JDSkill(BaseModel):
    name: str
    category: Literal["technical", "soft", "domain"]
    must_have: bool


class JDKeyword(BaseModel):
    term: str
    synonyms: List[str]
    importance: Importance


class JDExtraction(BaseModel):
    job_title: str
    company: str  # "" if not stated
    seniority: str
    location: str
    industry: str
    role_type: Literal["consulting", "product", "finance", "operations", "tech", "other"]
    responsibilities: List[str]
    required_qualifications: List[str]
    preferred_qualifications: List[str]
    skills: List[JDSkill]
    years_experience: str
    tools: List[str]
    industry_knowledge: List[str]
    keywords: List[JDKeyword]


# ---------- Stage 2: CV extraction ----------

class Contact(BaseModel):
    name: str
    emails: List[str]
    phones: List[str]
    location: str
    links: List[str]


class Education(BaseModel):
    institution: str
    degree: str
    field: str
    year: str
    grade: str


class Experience(BaseModel):
    employer: str
    title: str
    start: str
    end: str
    bullets: List[str]


class Project(BaseModel):
    name: str
    description: str


class MeasurableResult(BaseModel):
    result: str
    source_quote: str  # verbatim from CV


class CVExtraction(BaseModel):
    contact: Contact
    summary: str
    education: List[Education]
    experience: List[Experience]
    skills: List[str]
    projects: List[Project]
    achievements: List[str]
    certifications: List[str]
    measurable_results: List[MeasurableResult]
    total_years_experience: str


# ---------- Stage 4: Fit analysis ----------

DimensionKey = Literal[
    "experience", "responsibilities", "skills", "technical",
    "education", "industry", "leadership", "soft_skills",
]


class DimensionScore(BaseModel):
    dimension: DimensionKey
    score: int  # 0-10
    rationale: str
    evidence: List[str]


class RequirementMatch(BaseModel):
    requirement: str
    must_have: bool
    status: Literal["strong", "partial", "gap"]
    cv_evidence: str
    transferable_note: str
    claim_type: ClaimType


class FitAnalysis(BaseModel):
    dimensions: List[DimensionScore]
    requirements: List[RequirementMatch]
    summary: str


# ---------- Stage 5: Strengths, gaps, CV optimization ----------

class Resource(BaseModel):
    name: str
    url_or_search: str  # official URL if certain, otherwise a search phrase


class Strength(BaseModel):
    title: str
    evidence_quote: str
    jd_requirement: str
    explanation: str


class Gap(BaseModel):
    title: str
    severity: Literal["critical", "moderate", "minor"]
    why_it_matters: str
    close_short_term: str
    close_long_term: str
    interview_framing: str
    resources: List[Resource]


class StrengthsGaps(BaseModel):
    strengths: List[Strength]
    gaps: List[Gap]


class MissingKeyword(BaseModel):
    keyword: str
    recommendation: Literal["add_if_true", "genuine_gap"]
    note: str


class WeakStatement(BaseModel):
    original: str
    issue: str
    rewrite: str


class CVOptimization(BaseModel):
    missing_keywords: List[MissingKeyword]
    weak_statements: List[WeakStatement]
    tailored_cv_markdown: str
    change_notes: List[str]


# ---------- Stage 6: Research (parsed from free text, not structured outputs) ----------

class ResearchItem(BaseModel):
    topic: str
    statement: str
    source_url: str
    source_title: str = ""
    published_date: str = ""


class Research(BaseModel):
    subject: str
    identified: bool
    verified_facts: List[ResearchItem]
    analysis: List[str]
    interview_implications: List[str]
    notes: str = ""


# ---------- Stage 7: Interview prep & coaching ----------

class Question(BaseModel):
    category: Literal["hr_behavioral", "cv_based", "jd_based", "company", "technical", "follow_up"]
    question: str
    evaluating: str
    answer_guidance: str
    pitfalls: str
    priority: Literal["high", "medium", "low"]


class QuestionBank(BaseModel):
    questions: List[Question]
    feedback_guidance: List[str]


class FrameworkBranch(BaseModel):
    branch: str
    sub_points: List[str]


class RubricItem(BaseModel):
    criterion: str
    what_good_looks_like: str


class Case(BaseModel):
    case_type: Literal[
        "profitability", "market_entry", "growth_strategy", "pricing",
        "operations", "market_sizing", "business_problem",
    ]
    title: str
    prompt: str
    clarifying_questions: List[str]
    framework: List[FrameworkBranch]
    key_assumptions: List[str]
    model_answer_outline: List[str]
    rubric: List[RubricItem]


class CasePrep(BaseModel):
    cases: List[Case]


class CoachingAnswer(BaseModel):
    question: str
    answer: str
    tips: str


class STARStory(BaseModel):
    theme: Literal["leadership", "teamwork", "conflict", "failure", "problem_solving", "initiative", "achievement"]
    title: str
    cv_source: str
    backed_by_cv: bool
    situation: str
    task: str
    action: str
    result: str


class RedFlag(BaseModel):
    flag: str
    why_it_may_concern: str
    honest_response: str


class Coaching(BaseModel):
    answers: List[CoachingAnswer]
    stories: List[STARStory]
    red_flags: List[RedFlag]


# ---------- Stage 8: Plan & readiness ----------

class PlanDay(BaseModel):
    day: int
    focus: str
    tasks: List[str]
    practice: List[str]
    resources: List[Resource]
    time_estimate: str
    revision_focus: str


class TopAction(BaseModel):
    action: str
    rationale: str


class PrepPlan(BaseModel):
    days: List[PlanDay]
    top_actions: List[TopAction]
    competitive_advantages: List[str]
    interview_risks: List[str]
    top_priorities: List[str]
