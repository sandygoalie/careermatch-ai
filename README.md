# CareerMatch AI (Streamlit)

A Streamlit app that compares a job description (JD) with a candidate's CV and builds an interview-preparation report:

- job fit score
- ATS check
- CV rewrite
- interview and case questions
- company and industry research with sources
- STAR story bank
- 7-day preparation plan
- interview-readiness dashboard

The analysis runs on Claude through the Anthropic API.

> Career guidance and decision support only. No score is a probability of being hired.

## Setup

```bash
cd careermatch
pip install -r requirements.txt
```

Provide an Anthropic API key in one of three ways:

- **Environment variable:** `ANTHROPIC_API_KEY=sk-ant-...`
- **Secrets file:** copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.
- **Sidebar:** paste it into the password field. It's held only for that session.

## Run

```bash
streamlit run app.py
```

Then:
1. Click **Load sample JD + CV** to try the app with a fictional candidate.
2. Click **Analyze**. A full run takes a few minutes.
3. Move between the 13 sections in the sidebar.

## Inputs

| Input | Paste | Upload |
|---|---|---|
| Job description | ✅ | PDF, DOCX, TXT, DOC* |
| CV | ✅ | PDF, DOCX, DOC* |

\*DOC files are converted with LibreOffice if it's installed. Otherwise the app asks you to save the file as DOCX or PDF.

Scanned (image-only) PDFs contain no text to extract. The app detects them and asks you to paste the text instead.

## How it works

| Stage | What happens | Runs |
|---|---|---|
| 1 | JD and CV extraction (structured output) | in parallel |
| 2 | **Personal-detail redaction in code**: name, email, phone, links, address, and lines with protected characteristics (date of birth, marital status, gender, religion, …) | locally |
| 3 | Fit analysis, CV optimisation, company and industry research (web search), and case prep (consulting roles only) | in parallel |
| 4 | Strengths and gaps | |
| 5 | Interview question bank, and coaching (4 key answers, STAR stories, red flags) | in parallel |
| 6 | 7-day plan and dashboard inputs | |

Every Claude response is checked against a Pydantic schema (`schemas.py`) and retried once if it doesn't match. If one stage fails, only its section shows an error; the rest of the report still works.

### Models

| Setting | Detail |
|---|---|
| Default model | `claude-opus-5-5` |
| Alternative | `claude-sonnet-5-5` (faster and cheaper), selectable in the sidebar |
| Refusal fallback | Server-side `fallbacks: "default"`: if a safety filter declines a request, the API re-runs it on a recommended fallback model |

## Scoring (all computed in `scoring.py`, not by the AI)

| Score | Formula |
|---|---|
| **Job fit** | Claude rates 8 dimensions 0–10 with a rationale and CV evidence. Total = Σ(score/10 × weight) / Σweights × 100. Default weights: Experience 20, Responsibilities 15, Skills 15, Technical 15, Education 10, Industry 10, Leadership 8, Soft skills 7. You can change the weights with sliders, and the total recalculates without a new AI call. |
| **ATS readiness** | 50% keyword coverage (JD keywords plus synonyms, weighted must-have 2 / important 1 / nice-to-have 0.5) + 20% structure (standard headings, contact details, dates) + 20% quantified bullets (share containing a number) + 10% formatting (100 − 25 per risk flag: tables, images, header content, decorative symbols, merged columns) |
| **Interview readiness** (heuristic) | 40% fit + 20% ATS + 20% STAR coverage (share of 7 themes backed by the CV) + 20% gap score (100 − 25 per critical gap) |

## Guardrails

- **No invented candidate facts.** Prompts forbid adding qualifications, employers or numbers. Missing details appear as highlighted `[NEEDS INPUT: …]` placeholders.
- **No invented sources.** Each research item is kept only if its URL is one the web search tool actually retrieved. The rest are dropped, and the app shows how many were dropped.
- **Labelled claims.** Each item is tagged **Fact** (from the CV, JD or a cited source), **Assumption**, or **AI recommendation**.
- **Privacy.**
  - Personal details are removed before any analysis call.
  - Nothing is written to disk.
  - **Clear session** wipes the session's memory.
  - The tailored CV puts your name back in only on your own screen.

## Tests

```bash
python -m pytest -q
```

The tests don't call the API. They cover:
- the scoring formulas
- each file format, plus personal-detail redaction
- an end-to-end pipeline run with the API faked: source checking, a failure in one stage staying in that stage, the case section skipped for non-consulting roles, and the exports
- the real `app.py` driven with Streamlit's AppTest: load sample → Analyze → visit all 13 sections → change a weight

## Known limitations

- Scores are approximations for coaching, not what any particular ATS or recruiter would produce.
- Multi-column PDF layouts can merge text during extraction. Check the "Raw text as parsed" panels.
- Research quality depends on what web search returns. Little-known companies may get industry research only.
- A full run makes about 11 model calls (2 with web search). Expect a few minutes and some API cost per analysis, more on Opus than on Sonnet.

## Files

| File | Contents |
|---|---|
| `app.py` | Streamlit entry point: inputs, progress display, navigation, downloads |
| `pipeline.py` | Stage order, parallel runs, error isolation |
| `llm.py` | Anthropic SDK calls: structured output, web search, error messages |
| `research.py` | Company and industry research, source checking |
| `prompts.py` | All prompt text |
| `schemas.py` | Pydantic schemas for every stage |
| `scoring.py` | Fit, ATS and readiness formulas |
| `parsing.py` | PDF, DOCX, DOC and TXT reading, plus formatting-risk flags |
| `pii.py` | Personal-detail redaction |
| `export.py` | Markdown and JSON report, DOCX tailored CV |
| `ui/` | Section pages and UI components |
| `samples/` | Sample JD and fictional sample CV |
| `tests/` | Offline tests |
