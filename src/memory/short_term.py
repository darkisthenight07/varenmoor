"""Per-player short-term memory: a capped rolling buffer per character, persisted to JSON."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

MAX_ENTRIES = 10
_cache: dict[tuple[str, str], list[str]] = {}
_loaded: set[str] = set()


def _store_dir() -> Path:
    return Path(os.getenv("MEMORY_STORE_DIR", "./memory_store"))


def _path(player_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", player_id)
    return _store_dir() / f"st_{safe}.json"


def _ensure_loaded(player_id: str) -> None:
    if player_id in _loaded:
        return
    _loaded.add(player_id)
    path = _path(player_id)
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Ignoring unreadable short-term memory file %s: %s", path, exc)
        return
    for char, entries in raw.items():
        _cache.setdefault((player_id, char), list(entries)[-MAX_ENTRIES:])


def _save(player_id: str) -> None:
    snapshot = {c: e for (pid, c), e in _cache.items() if pid == player_id}
    try:
        path = _path(player_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("Could not persist short-term memory: %s", exc)


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
    """Clear the in-process cache (does not delete files). Mainly for tests."""
    _cache.clear()
    _loaded.clear()
