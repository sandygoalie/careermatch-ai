"""CareerMatch AI - Streamlit entry point.  Run:  streamlit run app.py"""

import os
from pathlib import Path

import streamlit as st

import scoring
from config import FIT_DIMENSIONS, SECTIONS
from export import report_json, report_markdown
from llm import LLMError
from parsing import ParseError, parse_input
from providers import OPENAI_COMPAT_PRESETS, PROVIDERS, list_models, make_provider
from pipeline import STAGES, dimension_scores, readiness, run_pipeline
from ui.components import current_weights, inject_css
from ui.sections import RENDERERS, SECTION_STAGE

st.set_page_config(page_title="CareerMatch AI", page_icon="🎯", layout="wide")
inject_css()

SAMPLES = Path(__file__).parent / "samples"
JD_TYPES = (".pdf", ".doc", ".docx", ".txt")
CV_TYPES = (".pdf", ".doc", ".docx")

ss = st.session_state
ss.setdefault("weights", {k: default for k, (_, default) in FIT_DIMENSIONS.items()})
ss.setdefault("report", None)
ss.setdefault("jd_text", "")
ss.setdefault("cv_text", "")


def _configured_key(names) -> str:
    """A key from environment variables or .streamlit/secrets.toml, if the host configured one."""
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
        try:
            if st.secrets.get(n):
                return st.secrets[n]
        except Exception:  # no secrets.toml
            pass
    return ""


OTHER_MODEL = "Other (type a model name)…"


def provider_settings():
    """Sidebar controls. Returns (kind, api_key, model, base_url, service, label) for the chosen provider."""
    kind = st.selectbox("AI provider", list(PROVIDERS), format_func=lambda k: PROVIDERS[k]["label"], key="provider")
    spec = PROVIDERS[kind]
    base_url = service = ""
    defaults = spec["models"]
    if kind == "openai_compat":
        service = st.selectbox("Service", list(OPENAI_COMPAT_PRESETS), key="service")
        preset_url, defaults = OPENAI_COMPAT_PRESETS[service]
        base_url = st.text_input("Base URL", value=preset_url, key=f"base_{service}")

    configured = _configured_key(spec["key_env"])
    if configured:
        api_key = configured
        st.success("API key configured by the host", icon="🔑")
    else:
        api_key = st.text_input(f"{spec['label'].split(' (')[0]} API key", type="password", key=f"key_{kind}",
                                help=spec["key_help"] + " Used only for this session; never stored or logged.")
        st.caption(spec["key_help"])

    fetched_key = f"models_{kind}_{service}"
    if st.button("🔄 Fetch my models", disabled=not (api_key or "localhost" in base_url),
                 help="List the models your key can use"):
        try:
            ss[fetched_key] = list_models(kind, api_key, base_url)
        except LLMError as e:
            st.error(str(e))
    options = ss.get(fetched_key) or defaults
    if defaults and ss.get(fetched_key):  # keep recommended defaults on top when available
        options = [m for m in defaults if m in options] + [m for m in options if m not in defaults]
    choice = st.selectbox("Model", options + [OTHER_MODEL], key=f"model_{kind}_{service}")
    model = st.text_input("Model name", key=f"custom_{kind}_{service}").strip() if choice == OTHER_MODEL else choice
    if kind == "openai_compat":
        st.caption("ℹ️ Company & industry web research isn't available with this provider; all other sections are.")
    return kind, api_key, model, base_url, service, spec["label"]


def clear_session():
    for k in list(ss.keys()):
        del ss[k]


def compute_scores(rep) -> dict:
    weights = current_weights()
    fit = scoring.fit_total(dimension_scores(rep), weights) if rep.fit else None
    return {"fit": fit, "ats": rep.ats.total if rep.ats else None, "readiness": readiness(rep, fit)}


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("🎯 CareerMatch AI")
    st.caption("JD-CV matcher · ATS checker · interview prep")
    kind, api_key, model, base_url, service, provider_label = provider_settings()

    rep = ss.report
    if rep:
        st.divider()
        def _label(s: str) -> str:
            stage = SECTION_STAGE.get(s)
            dot = "🔴" if stage in rep.errors else "⚪" if stage in rep.skipped else "🟢"
            return f"{dot} {s}"
        section = st.radio("Sections", SECTIONS, format_func=_label, key="nav")
        st.divider()
        scores = compute_scores(rep)
        st.download_button("⬇️ Full report (.md)", report_markdown(rep, scores), "careermatch_report.md", "text/markdown")
        st.download_button("⬇️ Full report (.json)", report_json(rep, scores), "careermatch_report.json", "application/json")
        if st.button("↩️ New analysis"):
            ss.report = None
            st.rerun()
    st.divider()
    if st.button("🗑️ Clear session", help="Wipes the inputs and results from memory"):
        clear_session()
        st.rerun()
    st.caption("Career guidance and decision support only - not a hiring decision. "
               "Your redacted CV is sent to the AI provider you choose and is not stored by this app.")


# ---------------------------------------------------------------- input view

def input_view():
    st.title("CareerMatch AI")
    st.write("Upload or paste a **job description** and your **CV**. You'll get a fit score, ATS check, CV rewrite, "
             "interview and case prep, cited company research, a STAR story bank and a 7-day plan.")
    if not api_key:
        st.info("🔑 **This app runs on your own AI key** - choose a provider in the sidebar and paste the key. "
                "It's used only for this browser session and never stored.\n\n"
                "- **No key yet?** Get a **free Google Gemini key** (no card needed) at https://aistudio.google.com/apikey\n"
                "- **Anthropic Claude**: paid key from https://console.anthropic.com (roughly $1-3 per analysis on Opus)\n"
                "- **Open-source models** via Groq or OpenRouter free tiers (web research is skipped for these)")
    if st.button("✨ Load sample JD + CV"):
        ss.jd_text = (SAMPLES / "sample_jd.txt").read_text(encoding="utf-8")
        ss.cv_text = (SAMPLES / "sample_cv.txt").read_text(encoding="utf-8")
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Job description")
        jd_file = st.file_uploader("Upload JD (PDF, DOC, DOCX, TXT)", type=[t[1:] for t in JD_TYPES], key="jd_file")
        st.text_area("…or paste the JD", key="jd_text", height=280)
    with c2:
        st.subheader("Your CV")
        cv_file = st.file_uploader("Upload CV (PDF, DOC, DOCX)", type=[t[1:] for t in CV_TYPES], key="cv_file")
        st.text_area("…or paste your CV", key="cv_text", height=280)
    company = st.text_input("Company name (only if the JD doesn't state it)", key="company_override")

    if not st.button("🔍 Analyze", type="primary", width="stretch"):
        return
    if not api_key and "localhost" not in base_url:
        st.error("Enter an API key in the sidebar first.")
        return
    if not model:
        st.error("Choose or type a model name in the sidebar.")
        return
    if kind == "openai_compat" and not base_url:
        st.error("Enter the service's base URL in the sidebar.")
        return
    try:
        jd_doc = parse_input(jd_file.name if jd_file else None, jd_file.getvalue() if jd_file else None, ss.jd_text, JD_TYPES)
    except ParseError as e:
        st.error(f"Job description: {e}")
        return
    try:
        cv_doc = parse_input(cv_file.name if cv_file else None, cv_file.getvalue() if cv_file else None, ss.cv_text, CV_TYPES)
    except ParseError as e:
        st.error(f"CV: {e}")
        return
    for w in jd_doc.warnings + cv_doc.warnings:
        st.warning(w)

    with st.status("Analysing… this usually takes a few minutes.", expanded=True) as status:
        rows = {k: st.empty() for k in STAGES}
        icons = {"running": "⏳", "done": "✅", "failed": "❌", "skipped": "➖"}
        for k, label in STAGES.items():
            rows[k].write(f"▫️ {label}")

        def progress(stage: str, state: str, detail: str):
            text = STAGES[stage] if state in ("running", "done") else f"{STAGES[stage]} - {detail}"
            rows[stage].write(f"{icons[state]} {text}")

        try:
            provider = make_provider(kind, api_key, model, base_url, service.split(" (")[0])
        except Exception as e:
            status.update(label="Couldn't start the AI provider", state="error")
            st.error(f"Couldn't set up {provider_label}: {e}")
            return
        rep = run_pipeline(provider, provider.description, jd_doc, cv_doc, company.strip(), progress)
        failed = not rep.jd or not rep.cv
        status.update(label="Analysis failed" if failed else "Analysis complete",
                      state="error" if failed else "complete", expanded=failed)
    if failed:
        st.error("Couldn't extract the JD or CV, so the analysis stopped: "
                 + "; ".join(f"{k}: {v}" for k, v in rep.errors.items()))
        return
    ss.report = rep
    ss.nav = "Overview"
    st.rerun()


# ---------------------------------------------------------------- report view

if ss.report is None:
    input_view()
else:
    rep = ss.report
    section = ss.get("nav", "Overview")
    st.title(section)
    RENDERERS[section](rep, compute_scores(rep))
