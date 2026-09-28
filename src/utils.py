from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict:
    """Best-effort JSON object extraction from LLM output (handles code fences and chatter).
    Returns {} if nothing parseable is found."""
    text = _FENCE.sub("", text.strip())
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)
