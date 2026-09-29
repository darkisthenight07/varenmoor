"""Emotion state (happiness, anger, trust) per (player, character), persisted to JSON."""
from __future__ import annotations

from . import store

EMOTIONS = ("happiness", "anger", "trust")
_DEFAULTS = {"happiness": 50, "anger": 20, "trust": 40}
_state: dict[tuple[str, str], dict[str, int]] = {}
_loaded: set[str] = set()


def _ensure_loaded(player_id: str) -> None:
    if player_id in _loaded:
        return
    _loaded.add(player_id)
    for char, emo in store.read_json(store.player_file("emo", player_id)).items():
        if isinstance(emo, dict):
            merged = dict(_DEFAULTS)
            merged.update({k: max(0, min(100, int(v))) for k, v in emo.items()
                           if k in _DEFAULTS and isinstance(v, (int, float))})
            _state.setdefault((player_id, char), merged)


def _save(player_id: str) -> None:
    store.write_json(store.player_file("emo", player_id),
                     {c: e for (pid, c), e in _state.items() if pid == player_id})


def get_emotions(player_id: str, char: str) -> dict[str, int]:
    _ensure_loaded(player_id)
    return dict(_state.setdefault((player_id, char), dict(_DEFAULTS)))


def update_emotions(player_id: str, char: str, delta: dict[str, int]) -> dict[str, int]:
    """Apply integer deltas, clamp each emotion to [0, 100], persist."""
    _ensure_loaded(player_id)
    current = _state.setdefault((player_id, char), dict(_DEFAULTS))
    for key, value in delta.items():
        if key in current:
            current[key] = max(0, min(100, current[key] + int(value)))
    _save(player_id)
    return dict(current)


def label(value: int) -> str:
    return "low" if value < 35 else "moderate" if value < 65 else "high"


def reset() -> None:
    """Clear the in-process cache (files are kept). Mainly for tests."""
    _state.clear()
    _loaded.clear()
