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

Visitors bring their own AI key and choose the provider:

| Provider | Key | Web research |
|---|---|---|
| **Google Gemini** (default) | **Free** at https://aistudio.google.com/apikey, no card needed | ✅ Google Search grounding |
| **Anthropic Claude** | Paid, from https://console.anthropic.com | ✅ Claude web search |
| **Open-source / OpenAI-compatible**: Groq, OpenRouter, Together, OpenAI, local Ollama | Free tiers on Groq and OpenRouter | ❌ the research sections are skipped |

**Fetch my models** in the sidebar lists the models your key can actually use, so changes to model names don't break the app.

> Career guidance and decision support only. No score is a probability of being hired.

## Setup

```bash
cd careermatch
pip install -r requirements.txt
```

Normally visitors paste their key into the sidebar, where it's held only for that session.

A host can preconfigure a key instead, through an environment variable or `.streamlit/secrets.toml`:
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

A preconfigured key means every visitor's analyses use the host's key.

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

Every AI response is checked against a Pydantic schema (`schemas.py`) and retried once if it doesn't match. If one stage fails, only its section shows an error; the rest of the report still works.

### How each provider gets structured output

| Provider | Structured output | Research | Other |
|---|---|---|---|
| **Gemini** | JSON-schema response mode | Google Search grounding. Google returns redirect links, which the app resolves to the real pages. A fact is kept only if its source domain was among the pages Google retrieved. | At most 3 calls at once, with automatic retries when a rate limit is hit |
| **Claude** | Native structured outputs | Server-side web search. A fact is kept only if its exact URL was retrieved. | If a safety filter declines a request, the API re-runs it on a recommended fallback model (`fallbacks: "default"`) |
| **OpenAI-compatible** | JSON mode plus the schema in the prompt. If the service rejects JSON mode, the app relies on the prompt alone. | Not available | At most 2 calls at once (free tiers have tight per-minute token limits) |

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
- A full run makes about 11 model calls (2 with web search). Expect a few minutes per analysis.
- **Free tiers have quotas.**
  - Gemini Flash's free daily request limit can be small, possibly enough for only one or two full analyses a day. Flash-Lite models usually allow more. You can see your project's limits at https://aistudio.google.com/rate-limit.
  - Groq's free tier limits tokens per minute, so large CVs or JDs can hit "request too large".
- **Open-source models** may follow the JSON format less reliably. The app retries once; if a stage still fails, only that section shows an error.

## Files

| File | Contents |
|---|---|
| `app.py` | Streamlit entry point: inputs, progress display, navigation, downloads |
| `pipeline.py` | Stage order, parallel runs, error isolation |
| `providers.py` | Gemini, Claude and OpenAI-compatible providers behind one interface, plus model listing |
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
