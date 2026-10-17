"""PII redaction done in code (not by the model) before any analysis stage."""

import re
from typing import Iterable, List, Tuple

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_TAIL = r"[^\s\"'<>()\[\]{},]+"
URL = re.compile(rf"(?:https?://|www\.){_URL_TAIL}|\b(?:linkedin\.com|github\.com|behance\.net)/{_URL_TAIL}", re.I)
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")

# Lines carrying protected characteristics are dropped entirely.
PROTECTED = re.compile(
    r"^\s*(?:date of birth|d\.?o\.?b\.?|age|gender|sex|marital status|religion|caste|"
    r"nationality|citizenship|father'?s name|mother'?s name|spouse|photo(?:graph)?|blood group)\b\s*[:\-].*$",
    re.I | re.M,
)

PROTECTED_LABELS = "date of birth, age, gender, marital status, religion, caste, nationality, family details, photo"


def _phone_repl(m: re.Match) -> str:
    """Only treat as a phone if it has 10+ digits and isn't a run of years like '2019 - 2021'."""
    s = m.group(0)
    groups = re.findall(r"\d+", s)
    if sum(len(g) for g in groups) < 10 or all(re.fullmatch(r"(19|20)\d{2}", g) for g in groups):
        return s
    return "[PHONE]"


def _name_variants(name: str) -> List[Tuple[str, int]]:
    """(pattern text, regex flags): full name case-insensitive, single name parts case-sensitive."""
    name = name.strip()
    if not name:
        return []
    parts = [p for p in re.split(r"\s+", name) if len(p) > 2 and p[0].isalpha()]
    return [(name, re.I)] + [(p, 0) for p in parts]  # full name first so it's replaced as one unit


def redact(text: str, name: str = "", location: str = "", extra: Iterable[str] = ()) -> Tuple[str, List[str]]:
    """Return (redacted_text, list of what was removed - categories only, never values)."""
    removed: List[str] = []

    def sub(pattern, repl, label, s, placeholder=None):
        new, n = pattern.subn(repl, s)
        if placeholder:  # count real replacements (a callable repl may leave matches unchanged)
            n = new.count(placeholder) - s.count(placeholder)
        if n:
            removed.append(f"{label} ({n})")
        return new

    text = sub(PROTECTED, "", "protected-characteristic lines", text)
    text = sub(EMAIL, "[EMAIL]", "emails", text)
    text = sub(URL, "[LINK]", "links", text)
    text = sub(PHONE, _phone_repl, "phone numbers", text, placeholder="[PHONE]")
    for value in [*extra]:
        if value and len(value) > 3:
            text = text.replace(value, "[REDACTED]")
    if location and len(location) > 3:
        text = sub(re.compile(re.escape(location), re.I), "[LOCATION]", "address/location", text)
    hits = 0
    for v, flags in _name_variants(name):
        text, n = re.subn(rf"\b{re.escape(v)}\b", "[CANDIDATE]", text, flags=flags)
        hits += n
    if hits:
        removed.append(f"candidate name ({hits})")
    return re.sub(r"\n{3,}", "\n\n", text).strip(), removed


def redact_data(data, **kw):
    """Redact every string inside nested dicts/lists (e.g. a model_dump()), leaving the structure intact."""
    if isinstance(data, str):
        return redact(data, **kw)[0] if data else data
    if isinstance(data, dict):
        return {k: redact_data(v, **kw) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_data(v, **kw) for v in data]
    return data


def restore_name(text: str, name: str) -> str:
    return text.replace("[CANDIDATE]", name) if name else text
