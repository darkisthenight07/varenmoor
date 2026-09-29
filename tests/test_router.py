import pytest

from varenmoor.llm.router import AllModelsFailed, Router
from varenmoor.llm.settings import parse_config

CFG = {
    "providers": {"a": {"kind": "groq", "api_key_env": "KEY_A"}, "b": {"kind": "mistral", "api_key_env": "KEY_B"},
                  "c": {"kind": "google", "api_key_env": "KEY_C"}},
    "models": {"m1": {"provider": "a", "model": "x"}, "m2": {"provider": "b", "model": "y"},
               "m3": {"provider": "c", "model": "z"}},
    "roles": {r: {"chain": ["m1", "m2", "m3"]} for r in
              ("narrator", "npc_dialogue", "input_review", "output_review", "memory")},
    "settings": {"cooldown_s": 30, "max_cooldown_s": 100},
}


class Clock:
    t = 1000.0
    def __call__(self): return self.t


class RateLimited(Exception):
    status_code = 429


class BadKey(Exception):
    status_code = 401


def make(behaviour, monkeypatch, keys=("KEY_A", "KEY_B", "KEY_C")):
    for k in ("KEY_A", "KEY_B", "KEY_C"):
        monkeypatch.delenv(k, raising=False)
    for k in keys:
        monkeypatch.setenv(k, "x")
    clock, log = Clock(), []

    class Client:
        def __init__(self, alias): self.alias = alias
        def invoke(self, prompt):
            log.append(self.alias)
            out = behaviour[self.alias]
            if isinstance(out, Exception): raise out
            return type("R", (), {"content": out})()

    router = Router(parse_config(CFG), clock=clock, client_factory=lambda cfg, alias, role, rl: Client(alias))
    return router, clock, log


def test_primary_used_when_healthy(monkeypatch):
    r, _, log = make({"m1": "one", "m2": "two", "m3": "three"}, monkeypatch)
    assert r.ask("narrator", "hi") == "one" and log == ["m1"]


def test_falls_over_on_error_and_benches_the_failing_model(monkeypatch):
    r, clock, log = make({"m1": RateLimited("429"), "m2": "two", "m3": "three"}, monkeypatch)
    assert r.ask("narrator", "hi") == "two" and log == ["m1", "m2"]
    log.clear()
    assert r.ask("narrator", "again") == "two"
    assert log == ["m2"]                      # m1 is cooling down, not retried
    clock.t += 31                             # cooldown over -> m1 gets another chance
    log.clear(); r.ask("narrator", "later")
    assert log[0] == "m1"


def test_cooldown_backs_off_exponentially_and_resets_on_success(monkeypatch):
    beh = {"m1": RateLimited("429"), "m2": "two", "m3": "three"}
    r, clock, _ = make(beh, monkeypatch)
    r.ask("narrator", "x")
    assert r.states["m1"].cooldown_until == clock.t + 30
    clock.t += 31; r.ask("narrator", "x")     # fails again -> 60s
    assert r.states["m1"].cooldown_until == clock.t + 60
    beh["m1"] = "back!"
    clock.t += 61
    assert r.ask("narrator", "x") == "back!"
    assert r.states["m1"].failures == 0


def test_bad_key_is_disabled_for_the_session(monkeypatch):
    r, clock, log = make({"m1": BadKey("401"), "m2": "two", "m3": "three"}, monkeypatch)
    r.ask("narrator", "x")
    clock.t += 10_000
    log.clear(); r.ask("narrator", "x")
    assert "m1" not in log


def test_empty_response_counts_as_failure(monkeypatch):
    r, _, log = make({"m1": "   ", "m2": "two", "m3": "three"}, monkeypatch)
    assert r.ask("memory", "x") == "two"


def test_models_without_keys_are_skipped(monkeypatch):
    r, _, log = make({"m1": "one", "m2": "two", "m3": "three"}, monkeypatch, keys=("KEY_B",))
    assert r.ask("narrator", "x") == "two" and log == ["m2"]


def test_no_keys_at_all_gives_actionable_error(monkeypatch):
    r, _, _ = make({"m1": "", "m2": "", "m3": ""}, monkeypatch, keys=())
    assert len(r.validate()) == 5
    with pytest.raises(AllModelsFailed, match="KEY_A"):
        r.ask("narrator", "x")


def test_all_failing_raises_with_every_reason(monkeypatch):
    r, _, _ = make({"m1": RateLimited("a"), "m2": RuntimeError("b"), "m3": RuntimeError("c")}, monkeypatch)
    with pytest.raises(AllModelsFailed) as e:
        r.ask("narrator", "x")
    assert all(k in str(e.value) for k in ("m1", "m2", "m3"))


def test_when_everything_is_cooling_down_it_still_probes_the_soonest(monkeypatch):
    beh = {"m1": RateLimited("a"), "m2": RateLimited("b"), "m3": RateLimited("c")}
    r, clock, log = make(beh, monkeypatch)
    with pytest.raises(AllModelsFailed):
        r.ask("narrator", "x")
    beh["m2"] = "recovered"                   # provider recovered before its cooldown expired
    assert r.ask("narrator", "x") == "recovered"


def test_stats_report_calls(monkeypatch):
    r, _, _ = make({"m1": RateLimited("a"), "m2": "two", "m3": "x"}, monkeypatch)
    r.ask("narrator", "x")
    s = r.stats()
    assert "narrator" in s and "m1" in s and "1 failure" in s
