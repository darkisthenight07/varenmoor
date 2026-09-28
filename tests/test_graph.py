from varenmoor.graph import build_agent
from varenmoor.memory import emotion, short_term
from varenmoor.state import initial_state


def test_full_turn_with_fake_llm(fake_llm):
    out = build_agent().invoke(initial_state("p1", "start", "Where am I?"))
    assert out["sanitized_input"] == "I look around the room."
    assert out["final_responses"] == {"doctor": "Leave this room."}
    assert out["advance_stage"] is False
    # memory + emotion side effects landed
    assert short_term.read("p1", "doctor") == ["Player looked around."]
    e = emotion.get_emotions("p1", "doctor")
    assert e["anger"] == 25 and e["trust"] == 38 and e["happiness"] == 51  # fenced JSON parsed, deltas applied


def test_narration_only_stage_skips_npcs(fake_llm):
    out = build_agent().invoke(initial_state("p1", "checkpoint3", "look"))
    assert out["final_responses"] == {}
