"""Single access point for chat models. Agents call get_llm() and never build models themselves."""
from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from . import config


@lru_cache(maxsize=None)
def get_llm() -> BaseChatModel:
    from langchain_groq import ChatGroq  # imported lazily so tests don't need a key
    return ChatGroq(model_name=config.DEFAULT_MODEL, temperature=config.DEFAULT_TEMPERATURE)


def text_of(response) -> str:
    """Extract plain text from a chat model response (handles block-list content)."""
    raw = getattr(response, "content", response)
    if isinstance(raw, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
            else b if isinstance(b, str) else ""
            for b in raw
        ).strip()
    return str(raw).strip()


def ask(prompt: str) -> str:
    """Send a prompt to the model and return stripped text."""
    return text_of(get_llm().invoke(prompt))
