"""Company and industry research: web-search calls plus strict source verification."""

from datetime import date
from typing import Tuple

from pydantic import ValidationError

import prompts
from llm import LLMError
from schemas import Research, ResearchItem


def research(client, model, system, prompt):
    """Dispatch to the provider's web-search call. Returns (parsed JSON, {retrieved_url: meta})."""
    return client.research(system, prompt)


def _norm_url(u: str) -> str:
    u = u.strip().split("#")[0].rstrip("/")
    return u.replace("http://", "https://").replace("://www.", "://").lower()


def verify(data: dict, retrieved: dict) -> Tuple[Research, int]:
    """Keep only facts whose URL was actually retrieved by the search tool. Returns (research, dropped_count)."""
    try:
        res = Research.model_validate(data)
    except ValidationError as e:
        raise LLMError(f"Research results were malformed: {str(e)[:200]}") from e
    lookup = {_norm_url(u): (u, meta) for u, meta in retrieved.items()}
    kept, dropped = [], 0
    for item in res.verified_facts:
        hit = lookup.get(_norm_url(item.source_url))
        if not hit:
            dropped += 1
            continue
        url, meta = hit
        kept.append(ResearchItem(
            topic=item.topic,
            statement=item.statement,
            source_url=url,
            source_title=item.source_title or meta.get("title", ""),
            published_date=item.published_date or (f"page age: {meta['page_age']}" if meta.get("page_age") else ""),
        ))
    res.verified_facts = kept
    return res, dropped


def company_research(client, model: str, system: str, company: str, role: str) -> Tuple[Research, int]:
    prompt = prompts.RESEARCH_COMPANY.format(company=company, role=role, today=date.today().isoformat())
    return verify(*research(client, model, system, prompt))


def industry_research(client, model: str, system: str, industry: str, role: str, company: str) -> Tuple[Research, int]:
    prompt = prompts.RESEARCH_INDUSTRY.format(
        industry=industry or "the employer's industry",
        role=role,
        company_clause=f" at {company}" if company else "",
        today=date.today().isoformat(),
    )
    return verify(*research(client, model, system, prompt))


def summary_for_prompts(company: Research | None, limit: int = 12) -> str:
    if not company or not company.verified_facts:
        return "(no verified company research available - avoid company-specific factual claims)"
    lines = [f"- {f.statement} (source: {f.source_title or f.source_url})" for f in company.verified_facts[:limit]]
    return "\n".join(lines)
