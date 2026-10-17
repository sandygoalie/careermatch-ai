"""One render function per report section."""

import difflib
import html
from typing import Dict, Optional

import pandas as pd
import streamlit as st

import pii
import scoring
from config import FIT_DIMENSIONS, FIT_DISCLAIMER, STAR_THEMES
from pipeline import Report, critical_gap_count
from ui.components import (
    card, current_weights, gauge, highlight_needs_input, md, progress_row, radar, stage_error, tag, tagged,
)

Scores = Dict[str, Optional[float]]
SEV_ORDER = ["critical", "moderate", "minor"]


def _bullets(items, kind: Optional[str] = None) -> str:
    if not items:
        return '<span class="cm-muted">None stated</span>'
    pre = tag(kind) + " " if kind else ""
    return "<ul>" + "".join(f"<li>{pre}{highlight_needs_input(str(i))}</li>" for i in items) + "</ul>"


# ---------------------------------------------------------------- 1. Overview

def overview(rep: Report, sc: Scores):
    jd = rep.jd
    st.subheader(f"{jd.job_title or 'Role'}" + (f" · {jd.company}" if jd.company else ""))
    st.caption(f"Generated {rep.created} · model {rep.model} · JD from {rep.jd_doc.source} · CV from {rep.cv_doc.source}")
    c1, c2, c3 = st.columns(3)
    with c1:
        gauge(sc["fit"], "Job fit", "ov_fit")
    with c2:
        gauge(sc["ats"], "ATS readiness", "ov_ats")
    with c3:
        gauge(sc["readiness"], "Interview readiness", "ov_ready")
    st.info(FIT_DISCLAIMER + " Readiness is a heuristic combining fit, ATS, story coverage and critical gaps.")

    if rep.fit:
        st.markdown("#### Summary")
        tagged("assumption", rep.fit.summary)
    c1, c2 = st.columns(2)
    with c1:
        if rep.sg:
            card("Top strengths", _bullets([s.title for s in rep.sg.strengths], "fact"))
    with c2:
        if rep.sg:
            gaps = sorted(rep.sg.gaps, key=lambda g: SEV_ORDER.index(g.severity))[:5]
            card("Most important gaps", _bullets([f"[{g.severity}] {g.title}" for g in gaps], "assumption"))

    if rep.errors:
        with st.expander(f"⚠️ {len(rep.errors)} section(s) had problems"):
            for k, v in rep.errors.items():
                st.write(f"**{k}**: {v}")
    with st.expander("🔒 Privacy: what was removed before analysis"):
        st.write("Personal details were replaced with placeholders in code before any analysis call. "
                 "Removed: " + (", ".join(rep.redaction_log) or "nothing detected") + ".")
        st.caption("Nothing is saved to disk by this app. Use 'Clear session' in the sidebar when you're done.")


# ---------------------------------------------------------------- 2. JD Analysis

def jd_analysis(rep: Report, sc: Scores):
    jd = rep.jd
    st.caption("Everything on this page is extracted from the JD you supplied.")
    cols = st.columns(4)
    for col, (label, val) in zip(cols, [("Title", jd.job_title), ("Company", jd.company or "not stated"),
                                        ("Seniority", jd.seniority or "-"), ("Role type", jd.role_type)]):
        col.metric(label, val or "-")
    st.write(f"**Industry:** {jd.industry or '-'} · **Location:** {jd.location or '-'} · "
             f"**Experience:** {jd.years_experience or '-'}")
    c1, c2 = st.columns(2)
    with c1:
        card("Responsibilities", _bullets(jd.responsibilities))
        card("Required qualifications", _bullets(jd.required_qualifications))
        card("Preferred qualifications", _bullets(jd.preferred_qualifications))
    with c2:
        st.markdown("**Skills**")
        st.dataframe(pd.DataFrame([{"Skill": s.name, "Type": s.category, "Must-have": "✅" if s.must_have else ""}
                                   for s in jd.skills]), hide_index=True, width="stretch")
        card("Tools", _bullets(jd.tools))
        card("Industry knowledge", _bullets(jd.industry_knowledge))
    with st.expander("ATS keywords extracted from the JD"):
        st.dataframe(pd.DataFrame([{"Keyword": k.term, "Importance": k.importance.replace("_", " "),
                                    "Synonyms": ", ".join(k.synonyms)} for k in jd.keywords]),
                     hide_index=True, width="stretch")
    with st.expander("Raw JD text as parsed"):
        st.text(rep.jd_doc.text)


# ---------------------------------------------------------------- 3. CV Analysis

def cv_analysis(rep: Report, sc: Scores):
    cv = rep.cv
    st.caption("Extracted from your CV (personal details redacted).")
    c1, c2, c3 = st.columns(3)
    c1.metric("Experience", cv.total_years_experience or "-")
    c2.metric("Roles", len(cv.experience))
    c3.metric("Quantified results", len(cv.measurable_results))
    if cv.summary:
        tagged("fact", cv.summary)
    st.markdown("#### Experience")
    for e in cv.experience:
        with st.expander(f"{e.title} · {e.employer} ({e.start} – {e.end})"):
            md(_bullets(e.bullets))
    c1, c2 = st.columns(2)
    with c1:
        card("Education", _bullets([f"{e.degree} {e.field}, {e.institution} {e.year} {e.grade}".strip() for e in cv.education]))
        card("Skills", _bullets(cv.skills))
        card("Certifications", _bullets(cv.certifications))
    with c2:
        card("Projects", _bullets([f"{p.name}: {p.description}" for p in cv.projects]))
        card("Achievements", _bullets(cv.achievements))
        card("Measurable results", _bullets([f"{m.result} — “{m.source_quote}”" for m in cv.measurable_results], "fact"))
    with st.expander("Redacted CV text used for analysis"):
        st.text(rep.cv_redacted)


# ---------------------------------------------------------------- 4. Fit Score

def fit_score(rep: Report, sc: Scores):
    if stage_error(rep, "fit"):
        return
    c1, c2 = st.columns([1, 1.4])
    with c1:
        gauge(sc["fit"], "Job fit", "fit_gauge")
        st.caption(FIT_DISCLAIMER)
    with c2:
        from pipeline import dimension_scores
        radar(dimension_scores(rep), "fit_radar")

    with st.expander("⚖️ Adjust dimension weights (recomputes instantly - no new AI call)"):
        ss = st.session_state
        cols = st.columns(4)
        for i, (k, (label, _)) in enumerate(FIT_DIMENSIONS.items()):
            ss.weights[k] = cols[i % 4].slider(label, 0, 40, value=ss.weights[k], key=f"sl_{k}")
        if st.button("Reset to default weights"):
            for k, (_, default) in FIT_DIMENSIONS.items():
                ss.weights[k] = default
                ss.pop(f"sl_{k}", None)
            st.rerun()
        st.caption("Weights are renormalised to 100. Total = Σ(score/10 × weight) / Σweights × 100.")

    st.markdown("#### Dimension scores")
    weights = current_weights()
    w_total = sum(weights.values()) or 1
    for d in sorted(rep.fit.dimensions, key=lambda d: list(FIT_DIMENSIONS).index(d.dimension)):
        label = FIT_DIMENSIONS[d.dimension][0]
        w = weights[d.dimension] / w_total * 100
        with st.expander(f"{label} - {d.score}/10 (weight {w:.0f}%)"):
            st.progress(d.score / 10)
            tagged("assumption", d.rationale)
            if d.evidence:
                md("<b>CV evidence</b>" + _bullets(d.evidence, "fact"))

    st.markdown("#### Requirement-by-requirement comparison")
    reqs = rep.fit.requirements
    counts = {s: sum(1 for r in reqs if r.status == s) for s in ("strong", "partial", "gap")}
    md(" ".join(tag(s, f"{s.title()}: {n}") for s, n in counts.items()))
    filt = st.multiselect("Show", ["strong", "partial", "gap"], default=["strong", "partial", "gap"], key="req_filter")
    rows = "".join(
        f"<tr><td>{html.escape(r.requirement)}</td><td>{'✅' if r.must_have else ''}</td><td>{tag(r.status)}</td>"
        f"<td>{html.escape(r.cv_evidence) or '<span class=cm-muted>-</span>'}</td>"
        f"<td>{tag(r.claim_type)} {html.escape(r.transferable_note)}</td></tr>"
        for r in reqs if r.status in filt
    )
    md("<table style='width:100%;font-size:0.88rem'><tr><th>Requirement</th><th>Must</th><th>Status</th>"
       f"<th>CV evidence</th><th>Transferable-skill note</th></tr>{rows}</table>")


# ---------------------------------------------------------------- 5. Strengths & Gaps

def strengths_gaps(rep: Report, sc: Scores):
    if stage_error(rep, "sg"):
        return
    st.markdown("#### Top 5 strengths")
    cols = st.columns(min(5, len(rep.sg.strengths)) or 1)
    for col, s in zip(cols, rep.sg.strengths):
        with col:
            card(s.title, f"{tag('fact')}<i>“{html.escape(s.evidence_quote)}”</i><br><br>"
                          f"<span class='cm-muted'>Serves: {html.escape(s.jd_requirement)}</span><br>{html.escape(s.explanation)}")
    st.markdown("#### Gaps")
    for sev in SEV_ORDER:
        gaps = [g for g in rep.sg.gaps if g.severity == sev]
        if not gaps:
            continue
        md(f"{tag(sev, f'{sev.title()} ({len(gaps)})')}")
        for g in gaps:
            with st.expander(g.title, expanded=sev == "critical"):
                md(f"<b>Why it matters:</b> {html.escape(g.why_it_matters)}")
                md(f"{tag('recommendation')}<b>Short term:</b> {html.escape(g.close_short_term)}")
                md(f"{tag('recommendation')}<b>Long term:</b> {html.escape(g.close_long_term)}")
                md(f"{tag('recommendation')}<b>In the interview:</b> {highlight_needs_input(g.interview_framing)}")
                if g.resources:
                    md("<b>Learning resources</b>" + _bullets([_resource(r) for r in g.resources]))


def _resource(r) -> str:
    u = r.url_or_search
    return f"{r.name} - {u}" if u.startswith("http") else f"{r.name} - search: “{u}”"


# ---------------------------------------------------------------- 6. CV Optimizer

def cv_optimizer(rep: Report, sc: Scores):
    a = rep.ats
    c1, c2 = st.columns([1, 1.5])
    with c1:
        gauge(a.total, "ATS readiness (approx.)", "ats_gauge")
    with c2:
        st.markdown("**How the ATS score is built**")
        progress_row("Keyword coverage (50%)", a.keywords, f"{sum(k.found for k in a.keyword_results)}/{len(a.keyword_results)} keywords")
        progress_row("Structure (20%)", a.structure)
        progress_row("Quantified impact (20%)", a.quantified, f"{a.quantified_counts[0]}/{a.quantified_counts[1]} bullets with a metric")
        progress_row("Formatting risk (10%)", a.formatting, f"{len(a.format_flags)} flag(s)")
    with st.expander("Score details"):
        st.write("**Structure checks:** " + ", ".join(f"{'✅' if v else '❌'} {k}" for k, v in a.structure_checks.items()))
        st.write("**Formatting flags:** " + ("; ".join(a.format_flags) or "none"))
        st.dataframe(pd.DataFrame([{"Keyword": k.term, "Importance": k.importance.replace("_", " "),
                                    "Found": "✅" if k.found else "❌", "Matched as": k.matched_as} for k in a.keyword_results]),
                     hide_index=True, width="stretch")

    if stage_error(rep, "cv_opt"):
        return
    opt = rep.cv_opt
    st.markdown("#### Missing keywords")
    if opt.missing_keywords:
        st.dataframe(pd.DataFrame([{"Keyword": k.keyword, "Advice": "Add if true" if k.recommendation == "add_if_true" else "Genuine gap",
                                    "Note": k.note} for k in opt.missing_keywords]), hide_index=True, width="stretch")
    else:
        st.success("No important keywords missing.")

    st.markdown("#### Weak or vague statements → rewrites")
    st.caption("Rewrites use only facts from your CV. Highlighted [NEEDS INPUT] spots need your real numbers or details.")
    for w in opt.weak_statements:
        md(f'<div class="cm-card"><span class="cm-muted">Original</span><br><s>{html.escape(w.original)}</s><br>'
           f'<span class="cm-muted">Issue: {html.escape(w.issue)}</span><br><br>{tag("recommendation", "Rewrite")}'
           f'{highlight_needs_input(w.rewrite)}</div>')

    st.markdown("#### Tailored CV")
    tailored = pii.restore_name(opt.tailored_cv_markdown, rep.candidate_name)
    t1, t2 = st.tabs(["Tailored CV", "Side-by-side with original"])
    with t1:
        st.markdown(tailored)
        st.code(tailored, language="markdown")
    with t2:
        l, r = st.columns(2)
        l.markdown("**Original**")
        l.text(rep.cv_doc.text)
        r.markdown("**Tailored**")
        r.text(tailored)
        with st.expander("Line diff"):
            diff = difflib.unified_diff(rep.cv_doc.text.splitlines(), tailored.splitlines(), "original", "tailored", lineterm="")
            st.code("\n".join(diff), language="diff")
    md("<b>What changed</b>" + _bullets(opt.change_notes, "recommendation"))
    from export import tailored_cv_docx
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Tailored CV (.md)", tailored.encode(), "tailored_cv.md", "text/markdown")
    d2.download_button("⬇️ Tailored CV (.docx)", tailored_cv_docx(opt.tailored_cv_markdown, rep.candidate_name),
                       "tailored_cv.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------- 7. Interview Questions

CATS = {"hr_behavioral": "HR / Behavioural", "cv_based": "CV-based", "jd_based": "JD-based",
        "company": "Company-specific", "technical": "Technical", "follow_up": "Difficult follow-ups"}


def interview_questions(rep: Report, sc: Scores):
    if stage_error(rep, "questions"):
        return
    qs = rep.questions.questions
    st.caption(f"{len(qs)} questions · {sum(q.priority == 'high' for q in qs)} high priority. "
               "This is a ready-to-use questionnaire, not a live interview.")
    high_only = st.toggle("Show high-priority only", key="q_high")
    tabs = st.tabs(list(CATS.values()) + ["🖨️ Printable questionnaire"])
    for tab, cat in zip(tabs, CATS):
        with tab:
            for q in [q for q in qs if q.category == cat and (not high_only or q.priority == "high")]:
                with st.expander(f"{'🔴' if q.priority == 'high' else '🟠' if q.priority == 'medium' else '⚪'} {q.question}"):
                    md(f"<b>What they're evaluating:</b> {html.escape(q.evaluating)}")
                    md(f"{tag('recommendation', 'Suggested answer')}{highlight_needs_input(q.answer_guidance)}")
                    md(f"<b>Pitfalls:</b> {html.escape(q.pitfalls)}")
    with tabs[-1]:
        lines = ["# Mock interview questionnaire", ""]
        for cat, label in CATS.items():
            lines.append(f"## {label}")
            for q in sorted([q for q in qs if q.category == cat], key=lambda q: ["high", "medium", "low"].index(q.priority)):
                lines += [f"**[{q.priority.upper()}] {q.question}**", f"- Evaluating: {q.evaluating}",
                          f"- Sample answer: {q.answer_guidance}", f"- Pitfalls: {q.pitfalls}",
                          "- My answer score (1-5): ___   Notes: ____________", ""]
        lines += ["## Self-feedback guidance"] + [f"- {x}" for x in rep.questions.feedback_guidance]
        text = "\n".join(lines)
        st.download_button("⬇️ Download questionnaire (.md)", text.encode(), "mock_interview_questionnaire.md", "text/markdown")
        st.markdown(text)


# ---------------------------------------------------------------- 8. Case Interview Prep

def case_prep(rep: Report, sc: Scores):
    if stage_error(rep, "cases"):
        return
    st.caption("Numbers in the cases are illustrative assumptions for practice, not facts.")
    for c in rep.cases.cases:
        with st.expander(f"{c.case_type.replace('_', ' ').title()}: {c.title}"):
            st.markdown(f"> {c.prompt}")
            c1, c2 = st.columns(2)
            with c1:
                md("<b>Clarifying questions</b>" + _bullets(c.clarifying_questions))
                md("<b>Issue tree</b><ul>" + "".join(
                    f"<li>{html.escape(b.branch)}<ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in b.sub_points) + "</ul></li>"
                    for b in c.framework) + "</ul>")
            with c2:
                md(f"{tag('assumption', 'Illustrative')}<b>Key assumptions</b>" + _bullets(c.key_assumptions))
                md("<b>Model answer outline</b><ol>" + "".join(f"<li>{html.escape(x)}</li>" for x in c.model_answer_outline) + "</ol>")
            st.dataframe(pd.DataFrame([{"Criterion": r.criterion, "What good looks like": r.what_good_looks_like} for r in c.rubric]),
                         hide_index=True, width="stretch")


# ---------------------------------------------------------------- 9/10. Research

def _research(rep: Report, key: str, res, dropped: int):
    if stage_error(rep, key):
        return
    st.caption(f"Research retrieved on {rep.created[:10]} via web search. Facts link to their sources; "
               "analysis and recommendations are AI-generated.")
    if not res.identified:
        st.warning(res.notes or "The subject couldn't be confidently identified.")
    t1, t2, t3 = st.tabs([f"Verified facts ({len(res.verified_facts)})", "Analysis", "What this means for your interview"])
    with t1:
        topics = list(dict.fromkeys(f.topic for f in res.verified_facts))
        for t in topics:
            st.markdown(f"**{t.replace('_', ' ').title()}**")
            for f in [f for f in res.verified_facts if f.topic == t]:
                date = f" · {html.escape(f.published_date)}" if f.published_date else " · date not stated"
                md(f"{tag('fact')}{html.escape(f.statement)} <span class='cm-muted'>— "
                   f"<a href='{html.escape(f.source_url)}' target='_blank'>{html.escape(f.source_title or f.source_url)}</a>{date}</span>")
        if dropped:
            st.caption(f"{dropped} item(s) were removed because their source URL wasn't among the pages actually retrieved.")
        if not res.verified_facts:
            st.info("No verifiable facts were returned.")
    with t2:
        md(_bullets(res.analysis, "assumption"))
    with t3:
        md(_bullets(res.interview_implications, "recommendation"))
    if res.notes and res.identified:
        st.caption(res.notes)


def company_research(rep: Report, sc: Scores):
    _research(rep, "company", rep.company, rep.company_dropped)


def industry_research(rep: Report, sc: Scores):
    _research(rep, "industry", rep.industry, rep.industry_dropped)


# ---------------------------------------------------------------- 11. Story Bank

def story_bank(rep: Report, sc: Scores):
    if stage_error(rep, "coaching"):
        return
    co = rep.coaching
    cov = scoring.story_coverage([s.model_dump() for s in co.stories])
    st.markdown("#### Tailored answers")
    for a in co.answers:
        with st.expander(a.question, expanded=False):
            md(f"{tag('recommendation')}{highlight_needs_input(a.answer)}")
            st.caption(f"Delivery tip: {a.tips}")
    st.markdown(f"#### STAR story bank · {cov:.0f}% of themes backed by your CV")
    by_theme = {s.theme: s for s in co.stories}
    for theme in STAR_THEMES:
        s = by_theme.get(theme)
        label = theme.replace("_", " ").title()
        if not s:
            st.write(f"**{label}**: not generated")
            continue
        icon = "✅" if s.backed_by_cv else "✍️"
        with st.expander(f"{icon} {label}: {s.title}"):
            st.caption(f"Based on: {s.cv_source}" if s.backed_by_cv else "No matching CV experience - recall one using the prompts below.")
            for part, val in (("Situation", s.situation), ("Task", s.task), ("Action", s.action), ("Result", s.result)):
                md(f"<b>{part}:</b> {highlight_needs_input(val)}")
    st.markdown("#### Potential CV red flags")
    if not co.red_flags:
        st.success("No significant red flags identified.")
    for r in co.red_flags:
        with st.expander(f"🚩 {r.flag}"):
            md(f"<b>Why it may concern an interviewer:</b> {html.escape(r.why_it_may_concern)}")
            md(f"{tag('recommendation', 'Honest response')}{highlight_needs_input(r.honest_response)}")


# ---------------------------------------------------------------- 12. Preparation Plan

def prep_plan(rep: Report, sc: Scores):
    if stage_error(rep, "plan"):
        return
    p = rep.plan
    st.markdown("#### The 3 most effective actions")
    cols = st.columns(len(p.top_actions) or 1)
    for col, (i, a) in zip(cols, enumerate(p.top_actions, 1)):
        with col:
            card(f"{i}. {a.action}", f"{tag('recommendation')}{html.escape(a.rationale)}")
    st.markdown("#### 7-day plan")
    for d in sorted(p.days, key=lambda d: d.day):
        done = sum(st.session_state.get(f"task_{d.day}_{i}", False) for i in range(len(d.tasks)))
        with st.expander(f"Day {d.day}: {d.focus} · {d.time_estimate} · {done}/{len(d.tasks)} done", expanded=d.day == 1):
            for i, t in enumerate(d.tasks):
                st.checkbox(t, key=f"task_{d.day}_{i}")
            md("<b>Practice</b>" + _bullets(d.practice))
            if d.resources:
                md("<b>Resources</b>" + _bullets([_resource(r) for r in d.resources]))
            st.caption(f"Revision focus: {d.revision_focus}")


# ---------------------------------------------------------------- 13. Interview Readiness

def readiness(rep: Report, sc: Scores):
    c1, c2, c3 = st.columns(3)
    with c1:
        gauge(sc["fit"], "Job fit", "rd_fit")
    with c2:
        gauge(sc["ats"], "ATS readiness", "rd_ats")
    with c3:
        gauge(sc["readiness"], "Interview readiness", "rd_ready")
    if sc["readiness"] is not None:
        stories = scoring.story_coverage([s.model_dump() for s in rep.coaching.stories])
        crit = critical_gap_count(rep)
        st.caption(f"Readiness (heuristic) = 40% fit ({sc['fit']:.0f}) + 20% ATS ({sc['ats']:.0f}) + "
                   f"20% story coverage ({stories:.0f}) + 20% gap score ({scoring.gap_score(crit):.0f}; {crit} critical gap(s)). "
                   "Not a probability of being hired.")
    c1, c2 = st.columns(2)
    with c1:
        if rep.sg:
            card("Strongest qualifications", _bullets([f"{s.title}: “{s.evidence_quote}”" for s in rep.sg.strengths], "fact"))
            gaps = sorted(rep.sg.gaps, key=lambda g: SEV_ORDER.index(g.severity))[:5]
            card("Most important skill gaps", _bullets([f"[{g.severity}] {g.title}" for g in gaps]))
    with c2:
        if rep.plan:
            card("Biggest interview risks", _bullets(rep.plan.interview_risks, "assumption"))
            card("Competitive advantages", _bullets(rep.plan.competitive_advantages, "assumption"))
            card("Top 3 preparation priorities", _bullets(rep.plan.top_priorities, "recommendation"))
    if rep.fit:
        from pipeline import dimension_scores
        radar(dimension_scores(rep), "rd_radar")


RENDERERS = {
    "Overview": overview, "JD Analysis": jd_analysis, "CV Analysis": cv_analysis, "Fit Score": fit_score,
    "Strengths & Gaps": strengths_gaps, "CV Optimizer": cv_optimizer, "Interview Questions": interview_questions,
    "Case Interview Prep": case_prep, "Company Research": company_research, "Industry Research": industry_research,
    "Story Bank": story_bank, "Preparation Plan": prep_plan, "Interview Readiness": readiness,
}

# Which pipeline stage feeds each section (for sidebar status dots).
SECTION_STAGE = {
    "Fit Score": "fit", "Strengths & Gaps": "sg", "CV Optimizer": "cv_opt", "Interview Questions": "questions",
    "Case Interview Prep": "cases", "Company Research": "company", "Industry Research": "industry",
    "Story Bank": "coaching", "Preparation Plan": "plan",
}
