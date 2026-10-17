"""Ordered analysis pipeline. Independent stages run in parallel; one stage failing never sinks the report."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pii
import prompts
import research as research_mod
import scoring
from llm import LLMError
from parsing import ParsedDoc
from schemas import (
    CasePrep, Coaching, CVExtraction, CVOptimization, FitAnalysis, JDExtraction,
    PrepPlan, QuestionBank, Research, StrengthsGaps,
)

STAGES = {
    "jd": "Extracting the job description",
    "cv": "Extracting the CV",
    "privacy": "Redacting personal details",
    "fit": "Scoring job fit",
    "cv_opt": "Optimising the CV",
    "company": "Researching the company (web search)",
    "industry": "Researching the industry (web search)",
    "cases": "Building case interview prep",
    "sg": "Analysing strengths & gaps",
    "questions": "Writing interview questions",
    "coaching": "Coaching answers & STAR stories",
    "plan": "Building the 7-day plan",
}


@dataclass
class Report:
    created: str
    model: str
    jd_doc: ParsedDoc
    cv_doc: ParsedDoc
    jd: Optional[JDExtraction] = None
    cv: Optional[CVExtraction] = None
    cv_redacted: str = ""
    redaction_log: List[str] = field(default_factory=list)
    candidate_name: str = ""
    ats: Optional[scoring.ATSResult] = None
    fit: Optional[FitAnalysis] = None
    cv_opt: Optional[CVOptimization] = None
    company: Optional[Research] = None
    company_dropped: int = 0
    industry: Optional[Research] = None
    industry_dropped: int = 0
    cases: Optional[CasePrep] = None
    sg: Optional[StrengthsGaps] = None
    questions: Optional[QuestionBank] = None
    coaching: Optional[Coaching] = None
    plan: Optional[PrepPlan] = None
    errors: Dict[str, str] = field(default_factory=dict)
    skipped: Dict[str, str] = field(default_factory=dict)

    @property
    def is_consulting(self) -> bool:
        return bool(self.jd and self.jd.role_type == "consulting")

    def to_dict(self) -> Dict[str, Any]:
        def dump(x):
            return x.model_dump() if x is not None and hasattr(x, "model_dump") else x

        out = {
            "created": self.created, "model": self.model,
            "jd_source": self.jd_doc.source, "cv_source": self.cv_doc.source,
            "redaction_log": self.redaction_log, "errors": self.errors, "skipped": self.skipped,
        }
        for k in ("jd", "fit", "cv_opt", "company", "industry", "cases", "sg", "questions", "coaching", "plan"):
            out[k] = dump(getattr(self, k))
        # CV extraction minus contact details.
        if self.cv:
            cv = self.cv.model_dump()
            cv.pop("contact", None)
            out["cv"] = cv
        if self.ats:
            a = self.ats
            out["ats"] = {
                "total": a.total, "keywords": a.keywords, "structure": a.structure,
                "quantified": a.quantified, "formatting": a.formatting,
                "missing_keywords": [k.term for k in a.missing_keywords], "format_flags": a.format_flags,
            }
        return out


Progress = Callable[[str, str, str], None]  # (stage, state: running|done|failed|skipped, detail)


def structured(client, model, system, prompt, schema, **kw):
    """`client` is a providers.* instance; `model` is kept for a uniform, easily faked signature."""
    return client.structured(system, prompt, schema, **kw)


def _j(model) -> str:
    return json.dumps(model.model_dump(), ensure_ascii=False, indent=1) if model else "(unavailable)"


def run_pipeline(client, model: str, jd_doc: ParsedDoc, cv_doc: ParsedDoc,
                 company_override: str, progress: Progress) -> Report:
    rep = Report(created=datetime.now().strftime("%Y-%m-%d %H:%M"), model=model, jd_doc=jd_doc, cv_doc=cv_doc)
    sysmsg = prompts.BASE_RULES

    def guarded(fn: Callable[[], Any]) -> tuple[Any, str]:
        """Runs in a worker thread: no UI calls here."""
        try:
            return fn(), ""
        except LLMError as e:
            return None, str(e)
        except Exception as e:  # keep the rest of the report alive
            return None, f"Unexpected error: {type(e).__name__}: {e}"

    def parallel(tasks: Dict[str, Callable[[], Any]]) -> Dict[str, Any]:
        """Progress is reported from this (main) thread only - Streamlit can't draw from workers."""
        for k in tasks:
            progress(k, "running", STAGES[k])
        out: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(len(tasks), getattr(client, "max_parallel", 8))) as ex:
            futs = {ex.submit(guarded, fn): k for k, fn in tasks.items()}
            for fut in as_completed(futs):
                k = futs[fut]
                out[k], err = fut.result()
                if err:
                    rep.errors[k] = err
                    progress(k, "failed", err)
                else:
                    progress(k, "done", STAGES[k])
        return out

    def call(key: str, fn: Callable[[], Any]):
        return parallel({key: fn})[key]

    def skip(key: str, why: str):
        rep.skipped[key] = why
        progress(key, "skipped", why)

    # --- Group 1: extraction ---
    hint = f' (if not stated, use "{company_override}")' if company_override else ""
    g1 = parallel({
        "jd": lambda: structured(client, model, sysmsg, prompts.JD_EXTRACT.format(jd=jd_doc.text, company_hint=hint),
                                 JDExtraction, effort="low"),
        "cv": lambda: structured(client, model, sysmsg, prompts.CV_EXTRACT.format(cv=cv_doc.text),
                                 CVExtraction, effort="low"),
    })
    rep.jd, rep.cv = g1["jd"], g1["cv"]
    if not rep.jd or not rep.cv:
        for k in list(STAGES)[2:]:
            skip(k, "Skipped because extraction failed")
        return rep
    if company_override:
        rep.jd.company = company_override

    # --- Privacy: redact in code before any analysis ---
    progress("privacy", "running", STAGES["privacy"])
    c = rep.cv.contact
    rep.candidate_name = c.name
    who = dict(name=c.name, location=c.location, extra=[*c.emails, *c.phones, *c.links])
    try:
        rep.cv_redacted, rep.redaction_log = pii.redact(cv_doc.text, **who)
        rep.cv = CVExtraction.model_validate(pii.redact_data(rep.cv.model_dump(), **who))
    except Exception as e:  # never continue to analysis with unredacted data
        rep.errors["privacy"] = f"Redaction failed ({type(e).__name__}); analysis stopped to protect your data."
        progress("privacy", "failed", rep.errors["privacy"])
        for k in list(STAGES)[3:]:
            skip(k, "Skipped because redaction failed")
        return rep
    progress("privacy", "done", STAGES["privacy"])

    bullets = [b for e in rep.cv.experience for b in e.bullets]
    rep.ats = scoring.ats_score([k.model_dump() for k in rep.jd.keywords], cv_doc.text, bullets, cv_doc.format_flags)

    context = prompts.CONTEXT.format(jd_json=_j(rep.jd), cv=rep.cv_redacted)
    role = rep.jd.job_title or "the advertised role"
    missing = ", ".join(k.term for k in rep.ats.missing_keywords) or "(none)"

    # --- Group 2: independent analyses + research ---
    g2_tasks: Dict[str, Callable[[], Any]] = {
        "fit": lambda: structured(client, model, sysmsg, prompts.FIT.format(context=context), FitAnalysis, effort="high"),
        "cv_opt": lambda: structured(client, model, sysmsg,
                                     prompts.CV_OPTIMIZE.format(context=context, missing=missing), CVOptimization),
    }
    if not getattr(client, "supports_search", True):
        no_search = "Web research needs a provider with search (Google Gemini or Anthropic Claude) - skipped"
        skip("industry", no_search)
        skip("company", no_search)
    else:
        g2_tasks["industry"] = lambda: research_mod.industry_research(client, model, sysmsg, rep.jd.industry, role,
                                                                      rep.jd.company)
        if rep.jd.company:
            g2_tasks["company"] = lambda: research_mod.company_research(client, model, sysmsg, rep.jd.company, role)
        else:
            skip("company", "No company name found in the JD - add one in the input form to enable company research")
    if rep.is_consulting:
        g2_tasks["cases"] = lambda: structured(client, model, sysmsg,
                                               prompts.CASES.format(industry=rep.jd.industry or "general", context=context),
                                               CasePrep)
    else:
        skip("cases", "Case interviews are only generated for consulting roles")
    g2 = parallel(g2_tasks)
    rep.fit, rep.cv_opt = g2.get("fit"), g2.get("cv_opt")
    if g2.get("company"):
        rep.company, rep.company_dropped = g2["company"]
    if g2.get("industry"):
        rep.industry, rep.industry_dropped = g2["industry"]
    rep.cases = g2.get("cases")

    # --- Group 3: strengths & gaps (needs fit) ---
    rep.sg = call("sg", lambda: structured(client, model, sysmsg,
                                           prompts.STRENGTHS_GAPS.format(fit_json=_j(rep.fit), context=context),
                                           StrengthsGaps, effort="high"))

    gaps_txt = "\n".join(f"- [{g.severity}] {g.title}: {g.why_it_matters}" for g in (rep.sg.gaps if rep.sg else [])) \
        or "(gap analysis unavailable)"
    research_txt = research_mod.summary_for_prompts(rep.company)

    # --- Group 4: interview prep & coaching ---
    g4 = parallel({
        "questions": lambda: structured(client, model, sysmsg,
                                        prompts.QUESTIONS.format(gaps=gaps_txt, research=research_txt, context=context),
                                        QuestionBank),
        "coaching": lambda: structured(client, model, sysmsg,
                                       prompts.COACHING.format(gaps=gaps_txt, research=research_txt, context=context),
                                       Coaching, effort="high"),
    })
    rep.questions, rep.coaching = g4["questions"], g4["coaching"]

    # --- Group 5: plan ---
    hp = [q.question for q in (rep.questions.questions if rep.questions else []) if q.priority == "high"]
    flags = [f"- {f.flag}" for f in (rep.coaching.red_flags if rep.coaching else [])]
    rep.plan = call("plan", lambda: structured(client, model, sysmsg, prompts.PLAN.format(
        sg_json=_j(rep.sg), questions="\n".join(f"- {q}" for q in hp) or "(unavailable)",
        red_flags="\n".join(flags) or "(none identified)",
        has_cases="yes - 7 consulting cases" if rep.cases else "no", context=context), PrepPlan))
    return rep


# ---------- derived numbers used by the UI ----------

def dimension_scores(rep: Report) -> Dict[str, float]:
    return {d.dimension: float(d.score) for d in rep.fit.dimensions} if rep.fit else {}


def critical_gap_count(rep: Report) -> int:
    return sum(1 for g in rep.sg.gaps if g.severity == "critical") if rep.sg else 0


def readiness(rep: Report, fit_score: Optional[float]) -> Optional[float]:
    if fit_score is None or rep.ats is None or rep.coaching is None or rep.sg is None:
        return None
    stories = scoring.story_coverage([s.model_dump() for s in rep.coaching.stories])
    return scoring.readiness_score(fit_score, rep.ats.total, stories, critical_gap_count(rep))
