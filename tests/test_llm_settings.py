import copy

import pytest
import yaml

from varenmoor.config import PACKAGED_MODELS
from varenmoor.llm.settings import ROLES, ConfigError, load_config, parse_config


def raw():
    return yaml.safe_load(PACKAGED_MODELS.read_text())


def test_packaged_config_is_valid_and_covers_all_roles():
    cfg = load_config(PACKAGED_MODELS)
    assert set(cfg.roles) == set(ROLES)
    assert cfg.pipeline.output_review == "on_flag"
    for role in cfg.roles.values():
        assert all(alias in cfg.models for alias in role.chain)


def test_every_role_ends_with_a_fallback():
    cfg = load_config(PACKAGED_MODELS)
    assert all(len(r.chain) >= 3 for r in cfg.roles.values())


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r["roles"]["narrator"]["chain"].append("nope"), "unknown model"),
    (lambda r: r["roles"].pop("memory"), "missing role"),
    (lambda r: r["roles"].update(bogus={"chain": ["groq-20b"]}), "unknown role"),
    (lambda r: r["roles"]["narrator"].update(chain=[]), "at least one"),
    (lambda r: r["models"]["groq-20b"].update(provider="ghost"), "not defined"),
    (lambda r: r["pipeline"].update(output_review="sometimes"), "output_review"),
    (lambda r: r["providers"]["groq"].update(kind="skynet"), "kind"),
    (lambda r: r["models"]["groq-20b"].update(rpm=-3), "rpm"),
    (lambda r: r["roles"]["narrator"].update(temprature=0.5), "unknown key"),
    (lambda r: r.update(modles={}), "unknown key"),
])
def test_bad_configs_are_rejected_with_clear_errors(mutate, msg):
    r = copy.deepcopy(raw())
    mutate(r)
    with pytest.raises(ConfigError, match=msg):
        parse_config(r)


def test_extra_model_keys_become_provider_params():
    cfg = load_config(PACKAGED_MODELS)
    assert cfg.models["groq-120b"].params == {"reasoning_effort": "low"}
