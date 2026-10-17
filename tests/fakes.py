"""Offline fakes: build valid schema instances without calling the API."""

import typing
from typing import get_args, get_origin

from pydantic import BaseModel

import schemas


def fake(model: type[BaseModel], i: int = 0) -> BaseModel:
    data = {}
    for name, f in model.model_fields.items():
        data[name] = _value(f.annotation, name, i)
    return model.model_validate(data)


def _value(tp, name: str, i: int):
    origin = get_origin(tp)
    if origin is typing.Literal:
        opts = get_args(tp)
        return opts[i % len(opts)]
    if origin in (list, typing.List):
        (inner,) = get_args(tp)
        return [_value(inner, name, j) for j in range(3)]
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return fake(tp, i).model_dump()
    if tp is bool:
        return True
    if tp is int:
        return 7 if name == "score" else i + 1
    return f"{name} {i} [NEEDS INPUT: detail]" if name in ("rewrite", "answer") else f"{name} {i}"


def fake_structured(client, model, system, prompt, schema, **kw):
    obj = fake(schema)
    if schema is schemas.JDExtraction:
        obj.company, obj.role_type, obj.industry = "Acme Corp", "consulting", "FMCG"
        obj.keywords = [schemas.JDKeyword(term="demand planning", synonyms=["forecasting"], importance="must_have"),
                        schemas.JDKeyword(term="Python", synonyms=[], importance="important")]
    if schema is schemas.CVExtraction:
        obj.contact = schemas.Contact(name="Ananya Rao", emails=["ananya.rao.sample@example.com"],
                                      phones=["+91 98765 43210"], location="Mumbai, Maharashtra",
                                      links=["linkedin.com/in/ananya-rao-sample", "https://github.com/ananya"])
        obj.experience[0].bullets = ["Reduced MAPE from 38% to 27%", "Worked with sales teams"]
        obj.projects[0].description = 'Portfolio at https://ananya.example/work, "quoted" [bracketed] text'
    if schema is schemas.FitAnalysis:
        keys = typing.get_args(schemas.DimensionKey)
        obj.dimensions = [schemas.DimensionScore(dimension=k, score=6, rationale="r", evidence=["e"]) for k in keys]
    if schema is schemas.Coaching:
        obj.stories = [schemas.STARStory(theme=t, title="t", cv_source="Northwind", backed_by_cv=True,
                                         situation="s", task="t", action="a", result="r") for t in
                       ["leadership", "teamwork", "conflict", "failure", "problem_solving"]]
    if schema is schemas.StrengthsGaps:
        obj.gaps[0].severity = "critical"
    return obj


def fake_research(client, model, system, prompt):
    data = {
        "subject": "Acme Corp", "identified": True,
        "verified_facts": [
            {"topic": "overview", "statement": "Acme makes widgets.", "source_url": "https://www.acme.example/about/",
             "source_title": "", "published_date": ""},
            {"topic": "strategy", "statement": "Made-up claim.", "source_url": "https://invented.example/x",
             "source_title": "Invented", "published_date": "2026-01-01"},
        ],
        "analysis": ["a"], "interview_implications": ["i"], "notes": "",
    }
    retrieved = {"https://acme.example/about": {"title": "About Acme", "page_age": "March 2026"}}
    return data, retrieved
