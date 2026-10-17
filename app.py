"""CareerMatch AI - Streamlit entry point.  Run:  streamlit run app.py"""

import os
from pathlib import Path

import streamlit as st

import scoring
from config import DEFAULT_MODEL_LABEL, FIT_DIMENSIONS, MODELS, SECTIONS
from export import report_json, report_markdown
from llm import make_client
from parsing import ParseError, parse_input
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


def _secret_key() -> str:
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:  # no secrets.toml
        return ""


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
    env_key = os.environ.get("ANTHROPIC_API_KEY") or _secret_key()
    if env_key:
        api_key = env_key
        st.success("API key loaded from environment", icon="🔑")
    else:
        api_key = st.text_input("Anthropic API key", type="password",
                                help="Used only for this session; never stored or logged.")
    model_label = st.selectbox("Model", list(MODELS), index=list(MODELS).index(DEFAULT_MODEL_LABEL))

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
               "Your CV is sent to the Anthropic API for analysis and is not stored by this app.")


# ---------------------------------------------------------------- input view

def input_view():
    st.title("CareerMatch AI")
    st.write("Upload or paste a **job description** and your **CV**. You'll get a fit score, ATS check, CV rewrite, "
             "interview and case prep, cited company research, a STAR story bank and a 7-day plan.")
    if not api_key:
        st.info("🔑 **This app runs on your own Anthropic API key.** Paste it in the sidebar - it's used only for "
                "this browser session and is never stored. Get a key at https://console.anthropic.com "
                "(a full analysis costs roughly $1-3 on Opus, less on Sonnet).")
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
    if not api_key:
        st.error("Enter an Anthropic API key in the sidebar first.")
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

        rep = run_pipeline(make_client(api_key), MODELS[model_label], jd_doc, cv_doc, company.strip(), progress)
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
