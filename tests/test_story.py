from varenmoor.story import ENDING, default_story


def test_loads_all_stages_in_order():
    s = default_story()
    assert [x.id for x in s.stages] == ["start"] + [f"checkpoint{i}" for i in range(1, 7)]
    assert s.characters == ["doctor", "mouse", "old_woman", "king"]


def test_next_ends_after_last_stage():
    s = default_story()
    assert s.next("start") == "checkpoint1"
    assert s.next("checkpoint6") == ENDING


def test_narration_only_stage_has_no_characters():
    assert default_story().stage("checkpoint3").characters == ()


def test_arc_marks_past_now_ahead():
    arc = default_story().arc_summary("checkpoint2")
    assert "PAST [start]" in arc and "NOW [checkpoint2]" in arc and "AHEAD [checkpoint6]" in arc
