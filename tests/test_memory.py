import pytest

from varenmoor import memory
from varenmoor.memory import emotion, long_term, short_term


def test_short_term_caps_and_persists(tmp_path):
    for i in range(15):
        short_term.write("p1", "doctor", f"e{i}")
    assert short_term.read("p1", "doctor") == [f"e{i}" for i in range(5, 15)]
    short_term.reset()  # simulate a new session: must reload from disk
    assert short_term.read("p1", "doctor")[-1] == "e14"


def test_short_term_is_scoped_per_player():
    short_term.write("a", "doctor", "x")
    assert short_term.read("b", "doctor") == []


def test_emotions_clamp():
    emotion.update_emotions("p", "doctor", {"anger": 500, "trust": -500})
    e = emotion.get_emotions("p", "doctor")
    assert e["anger"] == 100 and e["trust"] == 0


def test_long_term_is_noop_without_neo4j():
    long_term.write_relationship("p", "doctor", "FEARS", "player", 1, "ctx")
    assert long_term.read_relationships("p", "doctor") == []
    assert "No long-term memory" in memory.recall("p", "doctor")


def test_relation_validation_blocks_injection():
    assert long_term.normalize_relation("fears") == "FEARS"
    with pytest.raises(ValueError):
        long_term.normalize_relation("FEARS]->(x) DETACH DELETE x //")
