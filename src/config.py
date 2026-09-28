"""Environment-driven settings."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("VARENMOOR_MODEL", "llama-3.3-70b-versatile")
DEFAULT_TEMPERATURE = float(os.getenv("VARENMOOR_TEMPERATURE", "0.7"))
