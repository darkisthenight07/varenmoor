"""LLM access: agents call `ask(role, prompt)`; which model answers is decided by models.yaml."""
from __future__ import annotations

from ..config import models_file
from .router import AllModelsFailed, Router, text_of
from .settings import ROLES, ConfigError, LLMConfig, PipelineCfg, load_config

__all__ = ["ask", "get_router", "set_router", "pipeline", "reset", "text_of",
           "AllModelsFailed", "ConfigError", "LLMConfig", "PipelineCfg", "Router", "ROLES", "load_config"]

_router = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router(load_config(models_file()))
    return _router


def set_router(router) -> None:
    """Install a router (or a test double exposing .ask(role, prompt) and .pipeline)."""
    global _router
    _router = router


def reset() -> None:
    set_router(None)


def ask(role: str, prompt: str) -> str:
    return get_router().ask(role, prompt)


def pipeline() -> PipelineCfg:
    return get_router().pipeline
