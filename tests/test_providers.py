"""Provider adapters tested against fake SDK clients (no network)."""

import json
from types import SimpleNamespace as NS

import pytest

import providers
from fakes import fake
from llm import LLMError
from schemas import FitAnalysis, Research


def test_inline_schema_has_no_refs():
    s = json.dumps(providers.inline_schema(FitAnalysis))
    assert "$ref" not in s and "$defs" not in s and '"dimension"' in s


def _all_schemas():
    import schemas

    return [v for v in vars(schemas).values()
            if isinstance(v, type) and issubclass(v, schemas.BaseModel) and v is not schemas.BaseModel]


@pytest.mark.parametrize("schema", _all_schemas(), ids=lambda s: s.__name__)
def test_inline_schema_required_fields_all_defined(schema):
    """Regression: a field literally named 'title' was stripped along with pydantic's title labels."""
    def check(node, path="$"):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                missing = set(node.get("required", [])) - set(node.get("properties", {}))
                assert not missing, f"{schema.__name__} {path}: required but undefined {missing}"
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    inlined = providers.inline_schema(schema)
    check(inlined)
    assert not any(k == "title" and isinstance(v, str) for k, v in inlined.items())


# ---------------- Gemini

class FakeModels:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        return self.responses.pop(0)


def _gemini(responses):
    p = providers.GeminiProvider("k", "gemini-test")
    p.client = NS(models=FakeModels(responses))
    return p


def _resp(text, chunks=None, reason="STOP"):
    meta = NS(grounding_chunks=[NS(web=NS(uri=u, title=t, domain=d)) for u, t, d in (chunks or [])])
    return NS(text=text, candidates=[NS(finish_reason=reason, grounding_metadata=meta)])


def test_gemini_structured_retries_invalid_json():
    good = fake(FitAnalysis).model_dump_json()
    p = _gemini([_resp('{"dimensions": "oops"}'), _resp(good)])
    out = p.structured("sys", "prompt", FitAnalysis)
    assert isinstance(out, FitAnalysis)
    cfg = p.client.models.calls[0][2]
    assert cfg.response_mime_type == "application/json" and "$ref" not in json.dumps(cfg.response_json_schema)
    assert "previous answer was invalid" in p.client.models.calls[1][1]


def test_gemini_safety_block_is_readable():
    p = _gemini([_resp("", reason="FinishReason.SAFETY")])
    with pytest.raises(LLMError, match="safety"):
        p.structured("s", "p", FitAnalysis)


def test_gemini_research_maps_facts_to_grounded_pages(monkeypatch):
    resolved = {"https://vertexaisearch.example/r1": "https://www.acme.com/about-us",
                "https://vertexaisearch.example/r2": "https://news.example.org/acme-deal"}
    monkeypatch.setattr(providers, "_resolve_redirect", lambda u: resolved[u])
    data = {"subject": "Acme", "identified": True, "analysis": [], "interview_implications": [], "notes": "",
            "verified_facts": [
                {"topic": "overview", "statement": "Acme makes widgets", "source_url": "https://acme.com/company",
                 "source_title": "Acme", "published_date": ""},
                {"topic": "recent_developments", "statement": "Deal", "source_url": "https://news.example.org/acme-deal",
                 "source_title": "News", "published_date": "2026-09-01"},
                {"topic": "strategy", "statement": "Invented", "source_url": "https://madeup.example/x",
                 "source_title": "", "published_date": ""},
            ]}
    text = "Here you go\n```json\n" + json.dumps(data) + "\n```"
    p = _gemini([_resp(text, [("https://vertexaisearch.example/r1", "acme.com", "acme.com"),
                              ("https://vertexaisearch.example/r2", "news.example.org", "news.example.org")])])
    raw, retrieved = p.research("s", "p")

    import research as research_mod
    res, dropped = research_mod.verify(raw, retrieved)
    assert isinstance(res, Research)
    assert [f.source_url for f in res.verified_facts] == ["https://www.acme.com/about-us", "https://news.example.org/acme-deal"]
    assert dropped == 1  # the fact from a domain Google never retrieved


# ---------------- OpenAI-compatible

class FakeCompletions:
    def __init__(self, outputs, reject_json_mode=False):
        self.outputs, self.reject, self.calls = list(outputs), reject_json_mode, []

    def create(self, **kw):
        import httpx2
        import openai

        self.calls.append(kw)
        if self.reject and "response_format" in kw:
            req = httpx2.Request("POST", "https://x")
            raise openai.BadRequestError("response_format json_object not supported",
                                         response=httpx2.Response(400, request=req), body=None)
        return NS(choices=[NS(finish_reason="stop", message=NS(content=self.outputs.pop(0)))])


def _compat(outputs, reject=False):
    p = providers.OpenAICompatProvider("k", "llama-test", "https://api.example/v1", "Groq")
    p.client = NS(chat=NS(completions=FakeCompletions(outputs, reject)))
    return p


def test_openai_compat_structured_with_fenced_json():
    good = fake(FitAnalysis).model_dump_json()
    p = _compat(["```json\n" + good + "\n```"])
    assert isinstance(p.structured("s", "p", FitAnalysis), FitAnalysis)
    call = p.client.chat.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in call["messages"][1]["content"]


def test_openai_compat_falls_back_when_json_mode_unsupported():
    good = fake(FitAnalysis).model_dump_json()
    p = _compat([good], reject=True)
    assert isinstance(p.structured("s", "p", FitAnalysis), FitAnalysis)
    assert p._json_mode is False


def test_openai_compat_has_no_research():
    assert providers.OpenAICompatProvider.supports_search is False
    with pytest.raises(LLMError):
        _compat([]).research("s", "p")
