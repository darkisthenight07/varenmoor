"""Builds LangChain chat clients from config. Provider SDKs are imported lazily."""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

from .settings import LLMConfig, ProviderCfg, RoleCfg


def api_key(provider: ProviderCfg) -> str | None:
    return os.environ.get(provider.api_key_env) or None


def build_client(cfg: LLMConfig, alias: str, role: RoleCfg, rate_limiter=None) -> BaseChatModel:
    m = cfg.models[alias]
    p = cfg.providers[m.provider]
    key = api_key(p)
    if not key:
        raise RuntimeError(f"{p.api_key_env} is not set (needed for model '{alias}')")
    f = cfg.failover
    common = {"temperature": role.temperature, "max_retries": f.max_retries, "rate_limiter": rate_limiter}

    if p.kind == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=m.model, groq_api_key=key, max_tokens=role.max_tokens,
                        timeout=f.timeout_s, **common, **m.params)
    if p.kind == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=m.model, google_api_key=key, max_output_tokens=role.max_tokens,
                                      timeout=f.timeout_s, **common, **m.params)
    if p.kind == "mistral":
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(model=m.model, api_key=key, max_tokens=role.max_tokens,
                             timeout=int(f.timeout_s), **common, **m.params)
    if p.kind == "openai_compat":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=m.model, api_key=key, base_url=p.base_url, max_tokens=role.max_tokens,
                          timeout=f.timeout_s, **common, **m.params)
    raise ValueError(f"Unsupported provider kind {p.kind!r}")
