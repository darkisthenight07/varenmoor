import pytest

from varenmoor.story import ENDING, default_story, load_story


def test_loads_all_stages_in_order():
    s = default_story()
    assert [x.id for x in s.stages] == ["start", "checkpoint1", "checkpoint2", "checkpoint3", "checkpoint3b",
                                        "checkpoint4", "checkpoint5", "checkpoint6", "epilogue"]
    assert s.characters == ["doctor", "mouse", "old_woman", "king"]


def test_next_ends_after_last_stage():
    s = default_story()
    assert s.next("start") == "checkpoint1"
    assert s.next("epilogue") == ENDING


def test_every_stage_with_characters_has_a_player_beat_so_the_player_matters():
    for st in default_story().stages:
        if st.characters:
            assert any(b.by == "player" for b in st.beats), st.id


def test_cutscenes_have_no_characters_or_beats():
    s = default_story()
    assert s.stage("checkpoint3b").characters == () and s.stage("checkpoint3b").beats == ()
    assert s.stage("epilogue").beats == ()


def test_the_gallery_has_no_characters_but_waits_for_the_player():
    st = default_story().stage("checkpoint3")
    assert st.characters == () and [b.by for b in st.beats] == ["player"]


def test_arc_marks_past_now_ahead():
    arc = default_story().arc_summary("checkpoint2")
    assert "PAST [start]" in arc and "NOW [checkpoint2]" in arc and "AHEAD [checkpoint6]" in arc


def test_lore_is_director_only_and_environment_style_reaches_the_brief():
    s = default_story()
    assert "DIRECTOR-ONLY LORE" in s.scene_brief("checkpoint6")
    assert "NARRATION STYLE" in s.scene_brief("checkpoint3b")


def _write(tmp_path, body):
    p = tmp_path / "s.yaml"
    p.write_text(body)
    return p


def test_stage_without_beats_falls_back_to_one_player_beat_from_the_objective(tmp_path):
    p = _write(tmp_path, "stages:\n- id: a\n  description: x\n  characters: [bob]\n  objective: Be nice.\n"
                         "- id: b\n  description: y\n")
    a, b = load_story(p).stages
    assert [(x.by, x.text) for x in a.beats] == [("player", "Be nice.")] and b.beats == ()


@pytest.mark.parametrize("beat,msg", [
    ("{id: x, by: robot, text: t}", "npc or player"),
    ("{id: x, by: npc, text: t, who: nobody}", "not a character"),
    ("{id: x, text: t}\n  - {id: x, text: u}", "duplicate"),
])
def test_bad_beats_are_rejected(tmp_path, beat, msg):
    p = _write(tmp_path, f"stages:\n- id: a\n  description: x\n  characters: [bob]\n  beats:\n  - {beat}\n")
    with pytest.raises(ValueError, match=msg):
        load_story(p)


def test_npc_beat_needs_a_character(tmp_path):
    p = _write(tmp_path, "stages:\n- id: a\n  description: x\n  beats:\n  - {id: x, by: npc, text: t}\n")
    with pytest.raises(ValueError, match="no characters"):
        load_story(p)
