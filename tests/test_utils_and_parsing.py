from varenmoor.agents.director import parse_directives
from varenmoor.agents.narrator import parse_narration
from varenmoor.utils import parse_json_object


def test_json_plain_fenced_and_chatty():
    assert parse_json_object('{"a": 1}') == {"a": 1}
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! Here you go: {"a": 1} Hope that helps') == {"a": 1}
    assert parse_json_object("no json") == {}
    assert parse_json_object("[1, 2]") == {}


def test_parse_narration():
    text, adv = parse_narration("Dark hall.\nADVANCE: yes")
    assert text == "Dark hall." and adv is True
    assert parse_narration("Dark hall.\nADVANCE: no")[1] is False


def test_parse_directives():
    assert parse_directives("CHAR: Doctor\nPROMPT: Be curt.") == {"doctor": "Be curt."}
