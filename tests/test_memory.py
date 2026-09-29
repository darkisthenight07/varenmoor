import json

import pytest

from varenmoor import memory
from varenmoor.agents.memory_manager import apply_memory_update, consolidate
from varenmoor.memory import emotion, long_term, short_term, store


def test_short_term_caps_and_persists():
    for i in range(15):
        short_term.write("p1", "doctor", f"e{i}")
    assert short_term.read("p1", "doctor") == [f"e{i}" for i in range(5, 15)]
    short_term.reset()
    assert short_term.read("p1", "doctor")[-1] == "e14"


def test_short_term_is_scoped_per_player():
    short_term.write("a", "doctor", "x")
    assert short_term.read("b", "doctor") == []


def test_emotions_clamp():
    emotion.update_emotions("p", "doctor", {"anger": 500, "trust": -500})
    e = emotion.get_emotions("p", "doctor")
    assert e["anger"] == 100 and e["trust"] == 0


def test_emotions_persist_across_sessions():
    emotion.update_emotions("p", "doctor", {"anger": 30, "trust": -10})
    emotion.reset()                              # simulate restarting the game
    e = emotion.get_emotions("p", "doctor")
    assert e == {"happiness": 50, "anger": 50, "trust": 30}


def test_emotions_are_scoped_per_player_and_character():
    emotion.update_emotions("p", "doctor", {"anger": 30})
    emotion.reset()
    assert emotion.get_emotions("q", "doctor")["anger"] == 20
    assert emotion.get_emotions("p", "mouse")["anger"] == 20


def test_corrupt_emotion_file_falls_back_to_defaults(tmp_path):
    store.player_file("emo", "p").write_text("{not json")
    assert emotion.get_emotions("p", "doctor")["anger"] == 20


def test_writes_are_atomic_and_leave_no_temp_files(tmp_path):
    short_term.write("p", "doctor", "x")
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads(store.player_file("st", "p").read_text()) == {"doctor": ["x"]}


def test_long_term_is_noop_without_neo4j():
    long_term.write_relationship("p", "doctor", "FEARS", "player", 1, "ctx")
    assert long_term.read_relationships("p", "doctor") == []
    assert "No long-term memory" in memory.recall("p", "doctor")


def test_relation_validation_blocks_injection():
    assert long_term.normalize_relation("fears") == "FEARS"
    with pytest.raises(ValueError):
        long_term.normalize_relation("FEARS]->(x) DETACH DELETE x //")


def test_apply_memory_update_clamps_and_tolerates_garbage():
    apply_memory_update("p", "doctor", {"emotion": {"anger": 99, "trust": "abc"}, "short": "  hi  ", "long": {"relation": "X"}})
    e = emotion.get_emotions("p", "doctor")
    assert e["anger"] == 25 and e["trust"] == 40           # +5 clamp; garbage -> 0
    assert short_term.read("p", "doctor") == ["hi"]


def test_consolidate_makes_one_llm_call_and_survives_outage(fake):
    consolidate("p", "doctor", "hello", "leave")
    assert fake.roles_called() == ["memory"]
    assert emotion.get_emotions("p", "doctor")["anger"] == 25          # fenced JSON parsed
    fake.fail_roles.add("memory")
    consolidate("p", "doctor", "hello", "leave")                        # must not raise
