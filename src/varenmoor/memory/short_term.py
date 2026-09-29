"""Per-player short-term memory: a capped rolling buffer per character, persisted to JSON."""
from __future__ import annotations

from . import store

MAX_ENTRIES = 10
_cache: dict[tuple[str, str], list[str]] = {}
_loaded: set[str] = set()


def _ensure_loaded(player_id: str) -> None:
    if player_id in _loaded:
        return
    _loaded.add(player_id)
    for char, entries in store.read_json(store.player_file("st", player_id)).items():
        if isinstance(entries, list):
            _cache.setdefault((player_id, char), [str(e) for e in entries][-MAX_ENTRIES:])


def _save(player_id: str) -> None:
    store.write_json(store.player_file("st", player_id),
                     {c: e for (pid, c), e in _cache.items() if pid == player_id})


def read(player_id: str, char: str) -> list[str]:
    _ensure_loaded(player_id)
    return list(_cache.get((player_id, char), []))


def write(player_id: str, char: str, entry: str) -> None:
    _ensure_loaded(player_id)
    buf = _cache.setdefault((player_id, char), [])
    buf.append(entry)
    del buf[:-MAX_ENTRIES]
    _save(player_id)


def all_for_player(player_id: str) -> dict[str, list[str]]:
    _ensure_loaded(player_id)
    return {c: list(e) for (pid, c), e in _cache.items() if pid == player_id}


def reset() -> None:
    """Clear the in-process cache (files are kept). Mainly for tests."""
    _cache.clear()
    _loaded.clear()
