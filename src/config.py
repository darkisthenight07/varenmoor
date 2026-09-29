"""Environment loading and locating the models file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGED_MODELS = Path(__file__).parent / "models.yaml"


def models_file() -> Path:
    """VARENMOOR_MODELS_FILE > ./models.yaml > the copy shipped in the package."""
    env = os.getenv("VARENMOOR_MODELS_FILE")
    if env:
        p = Path(env).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"VARENMOOR_MODELS_FILE points to a missing file: {p}")
        return p
    local = Path.cwd() / "models.yaml"
    return local if local.exists() else PACKAGED_MODELS
