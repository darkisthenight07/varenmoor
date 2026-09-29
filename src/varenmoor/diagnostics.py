"""`varenmoor models`: show how each role is wired and (optionally) ping every model."""
from __future__ import annotations

import time

from . import llm
from .llm import providers


def show_models(ping: bool = False) -> int:
    router = llm.get_router()
    cfg = router.config
    print(f"Models file: {cfg.source}")
    print(f"Pipeline:    {cfg.pipeline}\n")
    for role, rc in cfg.roles.items():
        print(f"{role}  (temp {rc.temperature}, max_tokens {rc.max_tokens})")
        for i, alias in enumerate(rc.chain):
            m = cfg.models[alias]
            p = cfg.providers[m.provider]
            tag = "primary " if i == 0 else "fallback"
            if not router.has_key(alias):
                print(f"  {tag} {alias:<18} {m.model:<30} SKIPPED (set {p.api_key_env})")
                continue
            status = "key set"
            if ping:
                t0 = time.monotonic()
                try:
                    client = providers.build_client(cfg, alias, rc)
                    text = llm.text_of(client.invoke("Reply with the single word: OK"))
                    status = f"OK {time.monotonic() - t0:.1f}s ({text[:20]!r})" if text else "FAILED: empty response"
                except Exception as exc:
                    status = f"FAILED: {type(exc).__name__}: {str(exc)[:110]}"
            print(f"  {tag} {alias:<18} {m.model:<30} {status}")
        print()
    problems = router.validate()
    for p in problems:
        print(f"PROBLEM: {p}")
    return 1 if problems else 0
