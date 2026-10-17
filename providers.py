"""LLM providers behind one interface: structured(system, prompt, schema) and research(system, prompt).

- AnthropicProvider: Claude, with server-side web search.
- GeminiProvider: Google Gemini (free API keys available), with Google Search grounding.
- OpenAICompatProvider: any OpenAI-compatible endpoint (Groq, OpenRouter, OpenAI, Together, local Ollama)
  for open-source or other models. No web research.
"""

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Type, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

import llm
from llm import LLMError, _extract_json

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------- presets

PROVIDERS = {
    "gemini": {
        "label": "Google Gemini (free API key)",
        "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "key_help": "Free key, no card needed: https://aistudio.google.com/apikey",
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-4-argon"],
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "key_env": ("ANTHROPIC_API_KEY",),
        "key_help": "Paid key: https://console.anthropic.com",
        "models": ["claude-opus-5-5", "claude-sonnet-5-5"],
    },
    "openai_compat": {
        "label": "Open-source / OpenAI-compatible (Groq, OpenRouter, OpenAI, Ollama…)",
        "key_env": ("OPENAI_API_KEY",),
        "key_help": "Key from the service you pick below. Free tiers: Groq (console.groq.com), OpenRouter (openrouter.ai).",
        "models": [],
    },
}

OPENAI_COMPAT_PRESETS = {
    "Groq (free tier, open-source models)": ("https://api.groq.com/openai/v1",
                                             ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]),
    "OpenRouter (many models, some free)": ("https://openrouter.ai/api/v1",
                                            ["openai/gpt-oss-120b:free", "meta-llama/llama-3.3-70b-instruct:free"]),
    "OpenAI": ("https://api.openai.com/v1", []),
    "Together AI": ("https://api.together.xyz/v1", ["openai/gpt-oss-120b", "meta-llama/Llama-3.3-70B-Instruct-Turbo"]),
    "Ollama (local, only when running on your own machine)": ("http://localhost:11434/v1", ["llama3.3", "qwen3"]),
    "Custom endpoint": ("", []),
}

JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a single JSON object (no prose, no code fences) that validates against this JSON Schema:\n{schema}"
)


def inline_schema(schema: Type[BaseModel]) -> dict:
    """Pydantic JSON schema with $refs inlined - some providers don't resolve $defs."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


def _validate_with_retry(call, prompt: str, schema: Type[T]) -> T:
    """call(prompt) -> raw text. Validates, retrying once with the error appended."""
    last = ""
    for _ in range(2):
        text = call(prompt if not last else prompt + f"\n\nYour previous answer was invalid: {last}\nReturn corrected JSON only.")
        try:
            return schema.model_validate(_extract_json(text))
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last = str(e)[:1500]
    raise LLMError(f"Output didn't match the expected format after a retry: {last[:300]}")


# ---------------------------------------------------------------- Anthropic

class AnthropicProvider:
    supports_search = True
    max_parallel = 6

    def __init__(self, api_key: str, model: str):
        self.client = llm.make_client(api_key)
        self.model = model
        self.description = f"Anthropic · {model}"

    def structured(self, system, prompt, schema, effort="medium"):
        return llm.structured(self.client, self.model, system, prompt, schema, effort=effort)

    def research(self, system, prompt):
        return llm.research(self.client, self.model, system, prompt)


# ---------------------------------------------------------------- Gemini

def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _resolve_redirect(uri: str) -> str:
    """Gemini grounding links are Google redirect URLs; follow them to the real page."""
    try:
        req = urllib.request.Request(uri, method="HEAD", headers={"User-Agent": "Mozilla/5.0 CareerMatch"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.geturl()
    except Exception:
        return uri


class GeminiProvider:
    supports_search = True
    max_parallel = 3  # free-tier per-minute limits

    def __init__(self, api_key: str, model: str):
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=600_000,
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=8, max_delay=60,
                                                 http_status_codes=[429, 500, 502, 503, 504]),
        ))
        self.model = model
        self.description = f"Google Gemini · {model}"

    def _generate(self, system: str, prompt: str, **config):
        """Returns the full response (callers run in parallel threads, so nothing is stored on self)."""
        from google.genai import errors

        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=prompt,
                config=self.types.GenerateContentConfig(system_instruction=system, **config),
            )
        except errors.ClientError as e:
            raise LLMError(_gemini_error(e)) from e
        except errors.APIError as e:
            raise LLMError(f"Gemini API error ({getattr(e, 'code', '?')}). Try again shortly.") from e
        cand = (resp.candidates or [None])[0]
        reason = str(getattr(cand, "finish_reason", "") or "")
        if not resp.text:
            if "SAFETY" in reason or "PROHIBITED" in reason or "BLOCK" in reason:
                raise LLMError("Gemini declined this request (safety filter).")
            if "MAX_TOKENS" in reason:
                raise LLMError("Gemini's response was cut off at the output limit.")
            raise LLMError(f"Gemini returned an empty response ({reason or 'no reason given'}).")
        return resp

    def structured(self, system, prompt, schema, effort="medium"):
        js = inline_schema(schema)
        return _validate_with_retry(
            lambda p: self._generate(system, p, response_mime_type="application/json", response_json_schema=js).text,
            prompt, schema)

    def research(self, system, prompt) -> Tuple[dict, Dict[str, dict]]:
        resp = self._generate(system, prompt, tools=[self.types.Tool(google_search=self.types.GoogleSearch())])
        try:
            data = _extract_json(resp.text)
        except (ValueError, json.JSONDecodeError) as e:
            raise LLMError(f"Couldn't read the research results ({e}).") from e

        meta = getattr(resp.candidates[0], "grounding_metadata", None)
        chunks = [c.web for c in (getattr(meta, "grounding_chunks", None) or []) if getattr(c, "web", None)]
        with ThreadPoolExecutor(max_workers=8) as ex:
            finals = list(ex.map(_resolve_redirect, [c.uri for c in chunks]))
        retrieved: Dict[str, dict] = {}
        by_domain: Dict[str, str] = {}
        for c, final in zip(chunks, finals):
            retrieved[final] = {"title": c.title or c.domain or _domain(final), "page_age": ""}
            dom = (c.domain or c.title or _domain(final)).lower().removeprefix("www.")
            by_domain.setdefault(dom, final)
            by_domain.setdefault(_domain(final), final)

        # Gemini can't echo the exact grounded URL, so a fact counts as sourced when its domain
        # matches a page Google Search actually retrieved; the link then points to that page.
        for fact in data.get("verified_facts", []):
            url = fact.get("source_url", "")
            if url in retrieved:
                continue
            dom = _domain(url) if url.startswith("http") else url.lower()
            match = next((u for d, u in by_domain.items() if d and dom and (dom == d or dom.endswith("." + d) or d.endswith("." + dom))), None)
            if match:
                fact["source_url"] = match
        return data, retrieved


def _gemini_error(e) -> str:
    code = getattr(e, "code", None)
    msg = str(getattr(e, "message", "") or e)[:200]
    if code in (401, 403) or "API key" in msg:
        return "The Gemini API key was rejected. Check it in the sidebar."
    if code == 404:
        return f"Model '{msg}' not found - use 'Fetch my models' in the sidebar to pick an available one."
    if code == 429:
        return ("Gemini rate limit or daily free quota reached. Wait a minute (or until tomorrow for daily quota), "
                "or switch to a Flash-Lite model, which has a larger free allowance.")
    return f"Gemini rejected the request ({code}): {msg}"


# ---------------------------------------------------------------- OpenAI-compatible

class OpenAICompatProvider:
    supports_search = False
    max_parallel = 2  # free tiers have tight tokens-per-minute limits

    def __init__(self, api_key: str, model: str, base_url: str, service: str = ""):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=4, timeout=600)
        self.model = model
        self.description = f"{service or base_url} · {model}"
        self._json_mode = True

    def _chat(self, system: str, prompt: str) -> str:
        import openai

        kwargs = {"model": self.model, "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": prompt}]}
        try:
            if self._json_mode:
                try:
                    resp = self.client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
                except openai.BadRequestError as e:
                    if "response_format" not in str(e) and "json" not in str(e).lower():
                        raise
                    self._json_mode = False  # endpoint doesn't support JSON mode; rely on the prompt
                    resp = self.client.chat.completions.create(**kwargs)
            else:
                resp = self.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as e:
            raise LLMError("The API key was rejected by this service.") from e
        except openai.NotFoundError as e:
            raise LLMError("Model not found on this service - use 'Fetch my models' in the sidebar.") from e
        except openai.RateLimitError as e:
            raise LLMError("Rate limit or token-per-minute limit reached on this service's free tier. "
                           "Wait a minute and retry, or use Gemini.") from e
        except openai.APIStatusError as e:
            if e.status_code == 413:
                raise LLMError("Request too large for this model's free-tier token limit. Try Gemini or a paid tier.") from e
            raise LLMError(f"API error ({e.status_code}): {str(e)[:200]}") from e
        except openai.APIConnectionError as e:
            raise LLMError("Couldn't reach the service. Check the base URL and your connection.") from e
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("The response was cut off at the model's output limit.")
        return choice.message.content or ""

    def structured(self, system, prompt, schema, effort="medium"):
        suffix = JSON_INSTRUCTION.format(schema=json.dumps(inline_schema(schema)))
        return _validate_with_retry(lambda p: self._chat(system, p + suffix), prompt, schema)

    def research(self, system, prompt):
        raise LLMError("Web research isn't available with this provider.")


# ---------------------------------------------------------------- factory & model listing

def make_provider(kind: str, api_key: str, model: str, base_url: str = "", service: str = ""):
    if kind == "anthropic":
        return AnthropicProvider(api_key, model)
    if kind == "gemini":
        return GeminiProvider(api_key, model)
    return OpenAICompatProvider(api_key, model, base_url, service)


def list_models(kind: str, api_key: str, base_url: str = "") -> List[str]:
    """Models available to this key, for the sidebar picker. Raises LLMError with a readable message."""
    try:
        if kind == "gemini":
            from google import genai

            out = []
            for m in genai.Client(api_key=api_key).models.list():
                actions = getattr(m, "supported_actions", None) or []
                name = (m.name or "").removeprefix("models/")
                if "generateContent" in actions and "gemini" in name and not any(
                        x in name for x in ("image", "tts", "audio", "embedding", "live", "veo")):
                    out.append(name)
            return sorted(out, reverse=True)
        if kind == "anthropic":
            return [m.id for m in llm.make_client(api_key).models.list()]
        from openai import OpenAI

        return sorted(m.id for m in OpenAI(api_key=api_key or "not-needed", base_url=base_url).models.list())
    except Exception as e:
        raise LLMError(f"Couldn't list models ({type(e).__name__}): {str(e)[:200]}") from e
