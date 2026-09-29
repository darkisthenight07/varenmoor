"""Memory facade: short-term (JSON), long-term (Neo4j, optional) and emotions."""
from __future__ import annotations

from . import emotion, long_term, short_term
from .emotion import get_emotions, update_emotions

__all__ = [
    "emotion", "long_term", "short_term", "get_emotions", "update_emotions",
    "recall", "remember_short", "remember_relationship",
]


def recall(player_id: str, char: str) -> str:
    """Formatted short + long-term memory block, ready to inject into a prompt."""
    short = short_term.read(player_id, char)
    long = long_term.read_relationships(player_id, char)
    out = []
    out.append("Short-term:\n" + "\n".join(f"  - {s}" for s in short) if short else "[No short-term memory]")
    out.append("Long-term:\n" + "\n".join(f"  - {l}" for l in long) if long else "[No long-term memory]")
    return "\n\n".join(out)


def remember_short(player_id: str, char: str, text: str) -> None:
    short_term.write(player_id, char, text)


def remember_relationship(player_id: str, char: str, relation: str, target: str,
                          value: int, context: str) -> None:
    long_term.write_relationship(player_id, char, relation, target, value, context)
