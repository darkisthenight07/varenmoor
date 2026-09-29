"""Role-based LLM router with ordered fallback chains, cooldowns and request pacing."""
from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from langchain_core.rate_limiters import InMemoryRateLimiter

from .providers import api_key, build_client
from .settings import LLMConfig, PipelineCfg

log = logging.getLogger(__name__)

PERMANENT = float("inf")


class AllModelsFailed(RuntimeError):
    """Every model in a role's chain was unavailable or failed."""


class EmptyResponse(RuntimeError):
    pass


def text_of(response) -> str:
    """Plain text from a chat response; tolerates block-list content."""
    raw = getattr(response, "content", response)
    if isinstance(raw, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
            else b if isinstance(b, str) else ""
            for b in raw
        ).strip()
    return str(raw).strip()


def _status(exc: Exception) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        code = getattr(obj, "status_code", None)
        if isinstance(code, int):
            return code
    return None


@dataclass
class ModelState:
    alias: str
    limiter: InMemoryRateLimiter | None = None
    failures: int = 0            # consecutive failures
    cooldown_until: float = 0.0
    calls: int = 0
    errors: int = 0
    last_error: str = ""


class Router:
    def __init__(self, config: LLMConfig, *, clock: Callable[[], float] = time.monotonic,
                 client_factory: Callable | None = None):
        self.config = config
        self.pipeline: PipelineCfg = config.pipeline
        self._clock = clock
        self._factory = client_factory or build_client
        self._clients: dict[tuple[str, str], object] = {}
        self.role_calls: Counter[str] = Counter()
        self.states: dict[str, ModelState] = {}
        for alias, m in config.models.items():
            limiter = None
            if m.rpm:
                limiter = InMemoryRateLimiter(requests_per_second=m.rpm / 60.0,
                                              check_every_n_seconds=0.05,
                                              max_bucket_size=max(1.0, m.rpm / 6.0))
            self.states[alias] = ModelState(alias, limiter)

    # ── introspection ─────────────────────────────────────────────────────
    def has_key(self, alias: str) -> bool:
        m = self.config.models[alias]
        return api_key(self.config.providers[m.provider]) is not None

    def usable_chain(self, role: str) -> list[str]:
        return [a for a in self.config.roles[role].chain if self.has_key(a)]

    def missing_keys(self, role: str) -> list[str]:
        """Env vars that would need setting for this role to have any usable model."""
        return sorted({self.config.providers[self.config.models[a].provider].api_key_env
                       for a in self.config.roles[role].chain})

    def validate(self) -> list[str]:
        """Human-readable problems; empty list means every role has at least one usable model."""
        return [f"role '{r}' has no usable model; set one of: {', '.join(self.missing_keys(r))}"
                for r in self.config.roles if not self.usable_chain(r)]

    # ── calling ───────────────────────────────────────────────────────────
    def _client(self, alias: str, role: str):
        key = (alias, role)
        if key not in self._clients:
            self._clients[key] = self._factory(self.config, alias, self.config.roles[role],
                                               self.states[alias].limiter)
        return self._clients[key]

    def _fail(self, st: ModelState, exc: Exception) -> None:
        f = self.config.failover
        st.errors += 1
        st.failures += 1
        st.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        if _status(exc) in (401, 403):  # bad key: retrying is pointless this session
            st.cooldown_until = PERMANENT
        else:
            st.cooldown_until = self._clock() + min(f.cooldown_s * 2 ** (st.failures - 1), f.max_cooldown_s)

    def _attempt(self, alias: str, role: str, prompt: str) -> str:
        st = self.states[alias]
        st.calls += 1
        try:
            text = text_of(self._client(alias, role).invoke(prompt))
            if not text:
                raise EmptyResponse("model returned no text")
        except Exception as exc:
            self._fail(st, exc)
            log.info("%s: model %s failed (%s)", role, alias, st.last_error)
            raise
        st.failures, st.cooldown_until = 0, 0.0
        return text

    def ask(self, role: str, prompt: str) -> str:
        if role not in self.config.roles:
            raise KeyError(f"Unknown role {role!r}")
        chain = self.usable_chain(role)
        if not chain:
            raise AllModelsFailed(self.validate_role_message(role))
        self.role_calls[role] += 1
        now = self._clock()
        ready = [a for a in chain if self.states[a].cooldown_until <= now]
        benched = sorted((a for a in chain if a not in ready and self.states[a].cooldown_until != PERMANENT),
                         key=lambda a: self.states[a].cooldown_until)
        errors: list[str] = []
        # Healthy models first in priority order; if all are down, probe the ones whose cooldown ends soonest.
        for i, alias in enumerate(ready + benched):
            try:
                text = self._attempt(alias, role, prompt)
                if i > 0:
                    log.info("%s: served by fallback %s", role, alias)
                return text
            except Exception:
                errors.append(f"{alias}: {self.states[alias].last_error}")
        raise AllModelsFailed(f"All models for role '{role}' failed: " + " | ".join(errors))

    def validate_role_message(self, role: str) -> str:
        return f"Role '{role}' has no usable model; set one of: {', '.join(self.missing_keys(role))}"

    def stats(self) -> str:
        lines = ["LLM usage this session:"]
        lines += [f"  role {r:<13} {n} call(s)" for r, n in sorted(self.role_calls.items())]
        for a, s in self.states.items():
            if s.calls:
                lines.append(f"  model {a:<18} {s.calls} attempt(s), {s.errors} failure(s)"
                             + (f"  last: {s.last_error}" if s.errors else ""))
        return "\n".join(lines)
