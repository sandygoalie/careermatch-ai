"""Drive the real app.py: load sample -> Analyze (API faked) -> visit every section -> change a weight."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import pipeline
import research as research_mod
from config import SECTIONS
from fakes import fake_research, fake_structured

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_full_flow(monkeypatch):
    monkeypatch.setattr(pipeline, "structured", fake_structured)
    monkeypatch.setattr(research_mod, "research", fake_research)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # Gemini is the default provider

    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    next(b for b in at.button if "Load sample" in b.label).click().run()
    assert "Associate Consultant" in at.text_area[0].value
    next(b for b in at.button if "Analyze" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state.report is not None

    nav = at.sidebar.radio[0]
    for section in SECTIONS:
        nav.set_value(section).run()
        assert not at.exception, (section, [e.value for e in at.exception])
        assert at.title[0].value == section

    # Weight change recomputes fit without any API call, and survives leaving the page.
    nav.set_value("Fit Score").run()
    before = at.session_state.weights["experience"]
    at.slider(key="sl_experience").set_value(before + 10).run()
    assert at.session_state.weights["experience"] == before + 10
    nav.set_value("Overview").run()
    nav.set_value("Fit Score").run()
    assert at.slider(key="sl_experience").value == before + 10


def test_open_source_provider_skips_research(monkeypatch):
    monkeypatch.setattr(pipeline, "structured", fake_structured)
    monkeypatch.setattr(research_mod, "research", fake_research)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.selectbox(key="provider").set_value("openai_compat").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "api.groq.com" in next(t for t in at.sidebar.text_input if t.label == "Base URL").value
    next(b for b in at.button if "Load sample" in b.label).click().run()
    next(b for b in at.button if "Analyze" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    rep = at.session_state.report
    assert "company" in rep.skipped and "industry" in rep.skipped and rep.fit is not None
    assert "openai/gpt-oss-120b" in rep.model


def test_analyze_without_key_shows_error(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    next(b for b in at.button if "Load sample" in b.label).click().run()
    next(b for b in at.button if "Analyze" in b.label).click().run()
    assert any("API key" in e.value for e in at.error)
