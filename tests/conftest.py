import types

import pytest

from varenmoor import llm as llm_module
from varenmoor.memory import emotion, long_term, short_term


class FakeLLM:
    """Routes on prompt markers and returns canned, well-formed output."""

    def __init__(self):
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if "input reviewer" in prompt:
            text = "I look around the room."
        elif "Narrator and Story Orchestrator" in prompt:
            text = "Cold stone surrounds you.\nADVANCE: no"
        elif "Conversation Director" in prompt:
            text = "CHAR: doctor\nPROMPT: Be curt and dismissive."
        elif "emotion engine" in prompt:
            text = '```json\n{"happiness": 1, "anger": 9, "trust": -2}\n```'
        elif "memory system" in prompt:
            text = '{"short": "Player looked around.", "long": {"relation": "WARNED", "target": "player", "value": 2, "context": "told them to leave"}}'
        elif "Output Reviewer" in prompt:
            text = "Leave this room."
        else:
            text = "You are not the first to wake here."
        return types.SimpleNamespace(content=text)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_module, "get_llm", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_STORE_DIR", str(tmp_path))
    for var in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    long_term.close()
    long_term._disabled = False
    short_term.reset()
    emotion.reset()
    yield
    long_term._disabled = False
