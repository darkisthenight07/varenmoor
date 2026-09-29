"""Typed, validated view of models.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROLES = ("narrator", "npc_dialogue", "input_review", "output_review", "memory")
PROVIDER_KINDS = ("groq", "google", "mistral", "openai_compat")
INPUT_REVIEW_MODES = ("llm", "heuristic", "off")
OUTPUT_REVIEW_MODES = ("on_flag", "always", "off")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderCfg:
    name: str
    kind: str
    api_key_env: str
    base_url: str | None = None


@dataclass(frozen=True)
class ModelCfg:
    alias: str
    provider: str
    model: str
    rpm: float | None = None
    params: dict = field(default_factory=dict)  # passed through to the provider client


@dataclass(frozen=True)
class RoleCfg:
    name: str
    chain: tuple[str, ...]
    temperature: float = 0.7
    max_tokens: int = 500


@dataclass(frozen=True)
class PipelineCfg:
    input_review: str = "llm"
    output_review: str = "on_flag"
    background_memory: bool = True
    skip_memory_on_silence: bool = True


@dataclass(frozen=True)
class FailoverCfg:
    timeout_s: float = 45.0
    max_retries: int = 1
    cooldown_s: float = 30.0
    max_cooldown_s: float = 3600.0


@dataclass(frozen=True)
class LLMConfig:
    providers: dict[str, ProviderCfg]
    models: dict[str, ModelCfg]
    roles: dict[str, RoleCfg]
    pipeline: PipelineCfg = field(default_factory=PipelineCfg)
    failover: FailoverCfg = field(default_factory=FailoverCfg)
    source: str = "<memory>"


def _only(d: dict, allowed: set[str], where: str) -> None:
    extra = set(d) - allowed
    if extra:
        raise ConfigError(f"{where}: unknown key(s) {sorted(extra)}; allowed: {sorted(allowed)}")


def parse_config(raw: dict, source: str = "<memory>") -> LLMConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: top level must be a mapping")
    _only(raw, {"providers", "models", "roles", "pipeline", "settings"}, source)

    providers: dict[str, ProviderCfg] = {}
    for name, p in (raw.get("providers") or {}).items():
        _only(p, {"kind", "api_key_env", "base_url"}, f"providers.{name}")
        if p.get("kind") not in PROVIDER_KINDS:
            raise ConfigError(f"providers.{name}.kind must be one of {PROVIDER_KINDS}, got {p.get('kind')!r}")
        if not p.get("api_key_env"):
            raise ConfigError(f"providers.{name}.api_key_env is required")
        if p["kind"] == "openai_compat" and not p.get("base_url"):
            raise ConfigError(f"providers.{name}.base_url is required for openai_compat")
        providers[name] = ProviderCfg(name, p["kind"], p["api_key_env"], p.get("base_url"))

    models: dict[str, ModelCfg] = {}
    for alias, m in (raw.get("models") or {}).items():
        if not isinstance(m, dict) or "provider" not in m or "model" not in m:
            raise ConfigError(f"models.{alias} needs at least `provider` and `model`")
        if m["provider"] not in providers:
            raise ConfigError(f"models.{alias}.provider {m['provider']!r} is not defined under providers")
        extra = {k: v for k, v in m.items() if k not in {"provider", "model", "rpm"}}
        rpm = m.get("rpm")
        if rpm is not None and (not isinstance(rpm, (int, float)) or rpm <= 0):
            raise ConfigError(f"models.{alias}.rpm must be a positive number")
        models[alias] = ModelCfg(alias, m["provider"], str(m["model"]), rpm, extra)

    roles: dict[str, RoleCfg] = {}
    for name, r in (raw.get("roles") or {}).items():
        if name not in ROLES:
            raise ConfigError(f"roles.{name}: unknown role; valid roles: {list(ROLES)}")
        _only(r, {"chain", "temperature", "max_tokens"}, f"roles.{name}")
        chain = r.get("chain") or []
        if not chain:
            raise ConfigError(f"roles.{name}.chain must list at least one model")
        for alias in chain:
            if alias not in models:
                raise ConfigError(f"roles.{name}.chain references unknown model {alias!r}; defined: {sorted(models)}")
        roles[name] = RoleCfg(name, tuple(chain), float(r.get("temperature", 0.7)), int(r.get("max_tokens", 500)))
    missing = [r for r in ROLES if r not in roles]
    if missing:
        raise ConfigError(f"{source}: missing role(s): {missing}")

    pl = raw.get("pipeline") or {}
    _only(pl, {"input_review", "output_review", "background_memory", "skip_memory_on_silence"}, "pipeline")
    pipeline = PipelineCfg(
        input_review=str(pl.get("input_review", "llm")),
        output_review=str(pl.get("output_review", "on_flag")),
        background_memory=bool(pl.get("background_memory", True)),
        skip_memory_on_silence=bool(pl.get("skip_memory_on_silence", True)),
    )
    if pipeline.input_review not in INPUT_REVIEW_MODES:
        raise ConfigError(f"pipeline.input_review must be one of {INPUT_REVIEW_MODES}")
    if pipeline.output_review not in OUTPUT_REVIEW_MODES:
        raise ConfigError(f"pipeline.output_review must be one of {OUTPUT_REVIEW_MODES}")

    st = raw.get("settings") or {}
    _only(st, {"timeout_s", "max_retries", "cooldown_s", "max_cooldown_s"}, "settings")
    failover = FailoverCfg(**{k: type(getattr(FailoverCfg, k))(v) for k, v in st.items()})
    return LLMConfig(providers, models, roles, pipeline, failover, source)


def load_config(path: str | Path) -> LLMConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    return parse_config(raw, str(path))
