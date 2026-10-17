"""Central settings: Anthropic tool config, scoring weights, labels. (Provider/model choices live in providers.py.)"""

# Server-side refusal fallback: re-runs a declined request on a recommended model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Anthropic server-side web search tool (dynamic-filtering variant).
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}

# Fit-score dimensions: key -> (label, default weight). Weights sum to 100.
FIT_DIMENSIONS = {
    "experience": ("Experience", 20),
    "responsibilities": ("Job responsibilities", 15),
    "skills": ("Skills", 15),
    "technical": ("Technical skills / tools", 15),
    "education": ("Education & certifications", 10),
    "industry": ("Industry / domain knowledge", 10),
    "leadership": ("Leadership", 8),
    "soft_skills": ("Soft skills", 7),
}

# ATS component weights (fractions of 100).
ATS_WEIGHTS = {"keywords": 0.50, "structure": 0.20, "quantified": 0.20, "formatting": 0.10}

# Readiness heuristic weights.
READINESS_WEIGHTS = {"fit": 0.40, "ats": 0.20, "stories": 0.20, "gaps": 0.20}
CRITICAL_GAP_PENALTY = 25

STAR_THEMES = ["leadership", "teamwork", "conflict", "failure", "problem_solving", "initiative", "achievement"]

SECTIONS = [
    "Overview",
    "JD Analysis",
    "CV Analysis",
    "Fit Score",
    "Strengths & Gaps",
    "CV Optimizer",
    "Interview Questions",
    "Case Interview Prep",
    "Company Research",
    "Industry Research",
    "Story Bank",
    "Preparation Plan",
    "Interview Readiness",
]

FIT_DISCLAIMER = (
    "AI-estimated fit against the JD's stated requirements. "
    "This is not a probability of being shortlisted or hired."
)
