"""Small reusable UI pieces: tags, badges, gauges, cards."""

import html
from typing import Dict, Optional

import plotly.graph_objects as go
import streamlit as st

from config import FIT_DIMENSIONS

CSS = """
<style>
.cm-tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:0.72rem;font-weight:600;
        margin-right:6px;vertical-align:middle;border:1px solid transparent}
.cm-fact{background:#e3effd;color:#1b4f8f;border-color:#bcd6f7}
.cm-assumption{background:#eef0f3;color:#4a5260;border-color:#d6dae0}
.cm-recommendation{background:#f1e8fd;color:#5b2a9e;border-color:#dccaf7}
.cm-strong{background:#e3f6e9;color:#1d6b38;border-color:#b9e4c7}
.cm-partial{background:#fff4dc;color:#8a5a00;border-color:#f3dca6}
.cm-gap{background:#fde6e6;color:#a12828;border-color:#f3c1c1}
.cm-critical{background:#fde6e6;color:#a12828;border-color:#f3c1c1}
.cm-moderate{background:#fff4dc;color:#8a5a00;border-color:#f3dca6}
.cm-minor{background:#eef0f3;color:#4a5260;border-color:#d6dae0}
.cm-high{background:#fde6e6;color:#a12828;border-color:#f3c1c1}
.cm-medium{background:#fff4dc;color:#8a5a00;border-color:#f3dca6}
.cm-low{background:#eef0f3;color:#4a5260;border-color:#d6dae0}
.cm-needs{background:#fff3b0;color:#5c4a00;padding:0 3px;border-radius:3px}
.cm-card{border:1px solid rgba(128,128,128,0.25);border-radius:10px;padding:14px 16px;margin-bottom:10px;height:100%}
.cm-card h4{margin:0 0 6px 0;font-size:0.95rem}
.cm-muted{opacity:0.75;font-size:0.85rem}
</style>
"""

TAG_LABELS = {"fact": "Fact", "assumption": "Assumption", "recommendation": "AI recommendation"}


def current_weights() -> Dict[str, float]:
    """Live slider values win (they update before the script reruns); the stored copy survives page changes."""
    ss = st.session_state
    return {k: ss.get(f"sl_{k}", ss.weights[k]) for k in FIT_DIMENSIONS}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def tag(kind: str, label: Optional[str] = None) -> str:
    return f'<span class="cm-tag cm-{kind}">{html.escape(label or TAG_LABELS.get(kind, kind.replace("_", " ").title()))}</span>'


def highlight_needs_input(text: str) -> str:
    """Escape text and highlight [NEEDS INPUT: ...] placeholders."""
    import re

    esc = html.escape(text)
    return re.sub(r"\[NEEDS INPUT[^\]]*\]", lambda m: f'<span class="cm-needs">{m.group(0)}</span>', esc)


def md(html_text: str):
    st.markdown(html_text, unsafe_allow_html=True)


def tagged(kind: str, text: str):
    md(f"{tag(kind)} {highlight_needs_input(text)}")


def card(title: str, body_html: str):
    md(f'<div class="cm-card"><h4>{html.escape(title)}</h4>{body_html}</div>')


def score_color(v: float) -> str:
    return "#2e9e5b" if v >= 75 else "#d99a1e" if v >= 55 else "#d1495b"


def gauge(value: Optional[float], title: str, key: str):
    if value is None:
        st.metric(title, "n/a")
        return
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number={"suffix": "/100", "font": {"size": 30}},
        title={"text": title, "font": {"size": 15}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": score_color(value)},
               "steps": [{"range": [0, 55], "color": "rgba(209,73,91,0.10)"},
                         {"range": [55, 75], "color": "rgba(217,154,30,0.10)"},
                         {"range": [75, 100], "color": "rgba(46,158,91,0.10)"}]},
    ))
    fig.update_layout(height=210, margin=dict(l=20, r=20, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", key=key)


def radar(scores: Dict[str, float], key: str):
    keys = list(FIT_DIMENSIONS)
    labels = [FIT_DIMENSIONS[k][0] for k in keys]
    vals = [scores.get(k, 0) for k in keys]
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself",
                                    line_color="#3b6fd8", fillcolor="rgba(59,111,216,0.25)"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 10], tickvals=[2, 4, 6, 8, 10])),
                      height=360, margin=dict(l=60, r=60, t=30, b=30), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", key=key)


def progress_row(label: str, value: float, note: str = ""):
    c1, c2 = st.columns([3, 1])
    c1.progress(min(1.0, max(0.0, value / 100)), text=f"{label}{' - ' + note if note else ''}")
    c2.markdown(f"**{value:.0f}**/100")


def stage_error(rep, key: str) -> bool:
    """Show a stage's error/skip message. Returns True if the section has nothing to render."""
    if key in rep.errors:
        st.error(f"This section couldn't be generated: {rep.errors[key]}")
        return True
    if key in rep.skipped:
        st.info(rep.skipped[key])
        return True
    return False
