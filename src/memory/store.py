"""Tiny JSON persistence helpers shared by short-term memory and emotions."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def store_dir() -> Path:
    return Path(os.getenv("MEMORY_STORE_DIR", "./memory_store"))


def player_file(kind: str, player_id: str) -> Path:
    return store_dir() / f"{kind}_{re.sub(r'[^A-Za-z0-9_-]', '_', player_id)}.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Ignoring unreadable file %s: %s", path, exc)
        return {}


def write_json(path: Path, data: dict) -> None:
    """Atomic write (temp file + rename) so a crash can't leave a half-written file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("Could not persist %s: %s", path, exc)
