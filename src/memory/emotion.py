"""In-process emotion state (happiness, anger, trust), scoped per (player, character)."""
from __future__ import annotations

EMOTIONS = ("happiness", "anger", "trust")
_DEFAULTS = {"happiness": 50, "anger": 20, "trust": 40}
_state: dict[tuple[str, str], dict[str, int]] = {}


def get_emotions(player_id: str, char: str) -> dict[str, int]:
    return _state.setdefault((player_id, char), dict(_DEFAULTS))


def update_emotions(player_id: str, char: str, delta: dict[str, int]) -> dict[str, int]:
    """Apply integer deltas, clamping each emotion to [0, 100]."""
    current = get_emotions(player_id, char)
    for key, value in delta.items():
        if key in current:
            current[key] = max(0, min(100, current[key] + int(value)))
    return current


def label(value: int) -> str:
    return "low" if value < 35 else "moderate" if value < 65 else "high"


def reset() -> None:
    _state.clear()
