"""Thin wrapper around the Anthropic SDK: structured stage calls and web-search research calls."""

import json
import re
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from config import FALLBACK_BETA, WEB_SEARCH_TOOL

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """User-facing stage failure."""


def make_client(api_key: str | None) -> anthropic.Anthropic:
    # With no explicit key the SDK resolves ANTHROPIC_API_KEY or an `ant auth login` profile.
    return anthropic.Anthropic(api_key=api_key or None, max_retries=3, timeout=900)


def _describe_api_error(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "The Anthropic API key was rejected. Check it in the sidebar."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "This API key doesn't have access to the selected model or feature."
    if isinstance(e, anthropic.NotFoundError):
        return "Model or endpoint not found - check the model selection."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate limit reached. Wait a minute and run the analysis again."
    if isinstance(e, anthropic.BadRequestError):
        return f"The API rejected the request: {e.message}"
    if isinstance(e, anthropic.APIStatusError):
        return f"Anthropic API error ({e.status_code}). Try again shortly."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach the Anthropic API. Check your internet connection."
    return f"{type(e).__name__}: {e}"


def _check_stop(msg) -> None:
    if msg.stop_reason == "refusal":
        raise LLMError("The model declined this request (safety filter). Try rephrasing or removing unusual content.")
    if msg.stop_reason == "max_tokens":
        raise LLMError("The response was cut off at the output limit.")


def structured(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    prompt: str,
    schema: Type[T],
    effort: str = "medium",
    max_tokens: int = 64000,
) -> T:
    """One stage call returning a validated `schema` instance. Retries once on invalid output."""
    messages = [{"role": "user", "content": prompt}]
    last_err = ""
    for attempt in range(2):
        try:
            with client.beta.messages.stream(
                model=model,
                max_tokens=max_tokens,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=system,
                messages=messages,
                output_config={"effort": effort},
                output_format=schema,
            ) as stream:
                msg = stream.get_final_message()
            _check_stop(msg)
            if msg.parsed_output is None:
                raise ValueError("no structured output returned")
            return msg.parsed_output
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = str(e)[:1500]
            messages = [{
                "role": "user",
                "content": prompt + f"\n\nYour previous answer failed validation with: {last_err}\nReturn output that matches the schema exactly.",
            }]
        except LLMError:
            raise
        except anthropic.APIError as e:
            raise LLMError(_describe_api_error(e)) from e
    raise LLMError(f"Output didn't match the expected format after a retry: {last_err[:300]}")


def _extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    if not raw:
        raise ValueError("no JSON object found")
    return json.loads(raw)


def research(client: anthropic.Anthropic, model: str, system: str, prompt: str) -> tuple[dict, dict]:
    """Web-search call. Returns (parsed JSON dict, {url: {title, page_age}} of pages actually retrieved)."""
    messages = [{"role": "user", "content": prompt}]
    retrieved: dict[str, dict] = {}
    text_parts: list[str] = []
    try:
        for _ in range(6):  # resume server-tool turns that pause mid-way
            with client.beta.messages.stream(
                model=model,
                max_tokens=64000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=system,
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
                output_config={"effort": "medium"},
            ) as stream:
                msg = stream.get_final_message()
            for block in msg.content:
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    for r in block.content:
                        if getattr(r, "url", None):
                            retrieved[r.url] = {"title": r.title or "", "page_age": r.page_age or ""}
                elif block.type == "text":
                    text_parts.append(block.text)
                    for c in getattr(block, "citations", None) or []:
                        if getattr(c, "url", None):
                            retrieved.setdefault(c.url, {"title": getattr(c, "title", "") or "", "page_age": ""})
            if msg.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": msg.content})
            text_parts = []  # the resumed turn re-states its final answer
        _check_stop(msg)
    except LLMError:
        raise
    except anthropic.APIError as e:
        raise LLMError(_describe_api_error(e)) from e
    try:
        data = _extract_json("".join(text_parts))
    except (ValueError, json.JSONDecodeError) as e:
        raise LLMError(f"Couldn't read the research results ({e}).") from e
    return data, retrieved
