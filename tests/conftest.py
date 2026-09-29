import pytest

from varenmoor import llm
from varenmoor.llm.settings import PipelineCfg
from varenmoor.memory import emotion, long_term, short_term

DEFAULT_REPLIES = {
    "input_review": "I look around the room.",
    "narrator": "NARRATION: Cold stone surrounds you.\nADVANCE: no\nCHAR: doctor\nPROMPT: Be curt and dismissive.",
    "npc_dialogue": "You are not the first to wake here.",
    "output_review": "Leave this room.",
    "memory": ('```json\n{"emotion": {"happiness": 1, "anger": 9, "trust": -2}, "short": "Player looked around.", '
               '"long": {"relation": "WARNED", "target": "player", "value": 2, "context": "told them to leave"}}\n```'),
}


class FakeRouter:
    """Stands in for llm.Router: answers per role and records every call."""

    def __init__(self, pipeline=None, replies=None):
        self.pipeline = pipeline or PipelineCfg(background_memory=False)
        self.replies = {**DEFAULT_REPLIES, **(replies or {})}
        self.calls: list[tuple[str, str]] = []
        self.fail_roles: set[str] = set()

    def ask(self, role, prompt):
        self.calls.append((role, prompt))
        if role in self.fail_roles:
            raise llm.AllModelsFailed(f"role {role} down")
        return self.replies[role]

    def roles_called(self):
        return [r for r, _ in self.calls]

    def validate(self):
        return []


@pytest.fixture
def fake(monkeypatch):
    router = FakeRouter()
    llm.set_router(router)
    yield router
    llm.reset()


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_STORE_DIR", str(tmp_path))
    for var in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    long_term.close()
    long_term._disabled = False
    short_term.reset()
    emotion.reset()
    yield
    long_term._disabled = False
    llm.reset()
