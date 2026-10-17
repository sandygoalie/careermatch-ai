"""Deterministic score maths. No LLM calls here, so every number is reproducible."""

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from config import ATS_WEIGHTS, CRITICAL_GAP_PENALTY, READINESS_WEIGHTS, STAR_THEMES

# ---------- Fit ----------


def fit_total(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    """Weighted fit score 0-100 from 0-10 dimension scores. Weights are renormalised."""
    total_w = sum(w for k, w in weights.items() if k in scores)
    if total_w <= 0:
        return 0.0
    acc = sum(max(0.0, min(10.0, scores[k])) / 10 * w for k, w in weights.items() if k in scores)
    return round(acc / total_w * 100, 1)


# ---------- ATS ----------

_IMPORTANCE_WEIGHT = {"must_have": 2.0, "important": 1.0, "nice_to_have": 0.5}
_SUFFIXES = ("ing", "ers", "ies", "ed", "es", "er", "s")


def _stem(token: str) -> str:
    for suf in _SUFFIXES:
        if len(token) > len(suf) + 2 and token.endswith(suf):
            return token[: -len(suf)]
    return token


def _norm_tokens(text: str) -> List[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9+#.]+", text.lower().replace("-", " ")) if t.strip(".")]


def term_in_text(term: str, text_tokens_joined: str) -> bool:
    """Match a (possibly multi-word) term against pre-normalised text."""
    phrase = " ".join(_norm_tokens(term))
    if not phrase:
        return False
    return re.search(r"(?:^| )" + re.escape(phrase) + r"(?: |$)", text_tokens_joined) is not None


@dataclass
class KeywordResult:
    term: str
    importance: str
    found: bool
    matched_as: str = ""


def keyword_coverage(keywords: Iterable[dict], cv_text: str) -> tuple[float, List[KeywordResult]]:
    """keywords: dicts with term, synonyms, importance. Returns (0-100, per-keyword results)."""
    joined = " ".join(_norm_tokens(cv_text))
    results: List[KeywordResult] = []
    got = total = 0.0
    for kw in keywords:
        w = _IMPORTANCE_WEIGHT.get(kw.get("importance", "important"), 1.0)
        total += w
        match = next((t for t in [kw["term"], *kw.get("synonyms", [])] if term_in_text(t, joined)), "")
        if match:
            got += w
        results.append(KeywordResult(kw["term"], kw.get("importance", "important"), bool(match), match))
    return (round(got / total * 100, 1) if total else 0.0), results


_HEADINGS = {
    "experience": r"(work |professional )?experience|employment( history)?|work history",
    "education": r"education|academic",
    "skills": r"(key |technical |core )?skills|competenc",
    "summary": r"summary|profile|objective|about me",
}


def _looks_like_phone(s: str) -> bool:
    groups = re.findall(r"\d+", s)
    return sum(len(g) for g in groups) >= 10 and not all(re.fullmatch(r"(19|20)\d{2}", g) for g in groups)


def structure_score(cv_text: str) -> tuple[float, Dict[str, bool]]:
    lines = [l.strip().lower().strip(":") for l in cv_text.splitlines() if l.strip()]
    short = [l for l in lines if len(l) <= 40]
    checks = {f"'{k}' heading": any(re.fullmatch(rf"[\W\d]*({p})[\W]*", l) for l in short) for k, p in _HEADINGS.items()}
    checks["email present"] = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", cv_text) is not None
    checks["phone present"] = any(_looks_like_phone(m.group(0)) for m in re.finditer(r"\+?\d[\d\s().-]{8,}\d", cv_text))
    checks["dates detectable"] = len(re.findall(r"\b(19|20)\d{2}\b", cv_text)) >= 2
    return round(sum(checks.values()) / len(checks) * 100, 1), checks


_METRIC = re.compile(r"\d|%|\bpercent\b|₹|\$|€|£", re.I)


def quantified_score(bullets: List[str]) -> tuple[float, int, int]:
    bullets = [b for b in bullets if b.strip()]
    if not bullets:
        return 0.0, 0, 0
    n = sum(1 for b in bullets if _METRIC.search(b))
    return round(n / len(bullets) * 100, 1), n, len(bullets)


def formatting_score(flags: List[str]) -> float:
    return float(max(0, 100 - 25 * len(flags)))


@dataclass
class ATSResult:
    total: float
    keywords: float
    structure: float
    quantified: float
    formatting: float
    keyword_results: List[KeywordResult] = field(default_factory=list)
    structure_checks: Dict[str, bool] = field(default_factory=dict)
    quantified_counts: tuple = (0, 0)
    format_flags: List[str] = field(default_factory=list)

    @property
    def missing_keywords(self) -> List[KeywordResult]:
        return [k for k in self.keyword_results if not k.found]


def ats_score(keywords: Iterable[dict], cv_text: str, bullets: List[str], format_flags: List[str]) -> ATSResult:
    kw, kw_results = keyword_coverage(keywords, cv_text)
    st, checks = structure_score(cv_text)
    q, n, d = quantified_score(bullets)
    fm = formatting_score(format_flags)
    w = ATS_WEIGHTS
    total = round(w["keywords"] * kw + w["structure"] * st + w["quantified"] * q + w["formatting"] * fm, 1)
    return ATSResult(total, kw, st, q, fm, kw_results, checks, (n, d), list(format_flags))


# ---------- Readiness ----------


def story_coverage(stories: Iterable[dict]) -> float:
    """Share of the 7 STAR themes with at least one CV-backed story, 0-100."""
    backed = {s["theme"] for s in stories if s.get("backed_by_cv")}
    return round(len(backed & set(STAR_THEMES)) / len(STAR_THEMES) * 100, 1)


def gap_score(critical_gaps: int) -> float:
    return float(max(0, 100 - CRITICAL_GAP_PENALTY * critical_gaps))


def readiness_score(fit: float, ats: float, stories: float, critical_gaps: int) -> float:
    w = READINESS_WEIGHTS
    return round(w["fit"] * fit + w["ats"] * ats + w["stories"] * stories + w["gaps"] * gap_score(critical_gaps), 1)


def band(score: Optional[float]) -> str:
    if score is None:
        return "n/a"
    return "Strong" if score >= 75 else "Moderate" if score >= 55 else "Developing"
