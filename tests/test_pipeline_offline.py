"""End-to-end run with the API faked out: pipeline, verification, exports and every UI section."""

from pathlib import Path

import pytest

import pipeline
import research as research_mod
from fakes import fake_research, fake_structured
from parsing import parse_input

ROOT = Path(__file__).resolve().parent.parent
TXT = (".txt",)


@pytest.fixture
def report(monkeypatch):
    monkeypatch.setattr(pipeline, "structured", fake_structured)
    monkeypatch.setattr(research_mod, "research", fake_research)
    jd = parse_input("jd.txt", (ROOT / "samples" / "sample_jd.txt").read_bytes(), "", TXT)
    cv = parse_input("cv.txt", (ROOT / "samples" / "sample_cv.txt").read_bytes(), "", TXT)
    events = []
    rep = pipeline.run_pipeline(None, "fake-model", jd, cv, "", lambda *a: events.append(a))
    rep._events = events
    return rep


def test_all_stages_complete(report):
    assert report.errors == {}
    for k in ("jd", "cv", "fit", "cv_opt", "company", "industry", "cases", "sg", "questions", "coaching", "plan"):
        assert getattr(report, k) is not None, k
    assert {e[0] for e in report._events if e[1] == "done"} == set(pipeline.STAGES)


def test_privacy_applied_before_analysis(report):
    assert "Ananya" not in report.cv_redacted
    assert "Ananya" not in report.cv.model_dump_json()
    assert report.candidate_name == "Ananya Rao"


def test_unverified_sources_dropped(report):
    urls = [f.source_url for f in report.company.verified_facts]
    assert urls == ["https://acme.example/about"]
    assert report.company_dropped == 1
    assert report.company.verified_facts[0].source_title == "About Acme"


def test_non_consulting_skips_cases(monkeypatch):
    def jd_not_consulting(*a, **kw):
        obj = fake_structured(*a, **kw)
        if hasattr(obj, "role_type"):
            obj.role_type = "product"
        return obj

    monkeypatch.setattr(pipeline, "structured", jd_not_consulting)
    monkeypatch.setattr(research_mod, "research", fake_research)
    doc = parse_input(None, None, (ROOT / "samples" / "sample_cv.txt").read_text(encoding="utf-8"), TXT)
    rep = pipeline.run_pipeline(None, "m", doc, doc, "", lambda *a: None)
    assert rep.cases is None and "cases" in rep.skipped


def test_stage_failure_is_isolated(monkeypatch):
    from llm import LLMError
    from schemas import FitAnalysis

    def failing_fit(client, model, system, prompt, schema, **kw):
        if schema is FitAnalysis:
            raise LLMError("boom")
        return fake_structured(client, model, system, prompt, schema, **kw)

    monkeypatch.setattr(pipeline, "structured", failing_fit)
    monkeypatch.setattr(research_mod, "research", fake_research)
    doc = parse_input(None, None, (ROOT / "samples" / "sample_cv.txt").read_text(encoding="utf-8"), TXT)
    rep = pipeline.run_pipeline(None, "m", doc, doc, "", lambda *a: None)
    assert rep.errors == {"fit": "boom"}
    assert rep.plan is not None and rep.questions is not None


def test_exports(report):
    import json

    from export import report_json, report_markdown, tailored_cv_docx

    scores = {"fit": 60.0, "ats": 50.0, "readiness": 55.0}
    md = report_markdown(report, scores).decode()
    assert "## Scores" in md and "not a probability" in md.lower()
    data = json.loads(report_json(report, scores))
    assert "contact" not in data["cv"]
    assert tailored_cv_docx("# Name\n## Experience\n- **Did** a thing", "Ananya")[:2] == b"PK"


def test_every_section_renders(report):
    from streamlit.testing.v1 import AppTest

    def script():
        import streamlit as st

        from config import FIT_DIMENSIONS, SECTIONS
        from ui.components import inject_css
        from ui.sections import RENDERERS

        inject_css()
        st.session_state.setdefault("weights", {k: w for k, (_, w) in FIT_DIMENSIONS.items()})
        rep = st.session_state.rep
        for s in SECTIONS:
            st.header(s)
            RENDERERS[s](rep, {"fit": 61.0, "ats": 52.0, "readiness": 58.0})

    at = AppTest.from_function(script, default_timeout=60)
    at.session_state.rep = report
    at.run()
    assert not at.exception, [e.value for e in at.exception]
