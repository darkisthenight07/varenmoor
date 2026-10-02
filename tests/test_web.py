import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from varenmoor.web import app  # noqa: E402


def test_session_opens_the_scene_and_messages_return_events(fake):
    c = TestClient(app)
    r = c.post("/api/session", json={"player": "Tester"}).json()
    assert [e["kind"] for e in r["events"]] == ["narration"]          # the narrator opens; nobody speaks yet
    m = c.post(f"/api/session/{r['session_id']}/message", json={"text": "Where am I?"}).json()
    assert [e["speaker"] for e in m["events"] if e["kind"] == "say"] == ["doctor"]
    assert m["finished"] is False and {e["kind"] for e in m["events"]} <= {"narration", "say", "end"}
    assert "emotions" not in m and "scene" not in m


def test_unknown_session_is_404(fake):
    assert TestClient(app).post("/api/session/nope/message", json={"text": "hi"}).status_code == 404


def test_outage_is_a_503_not_a_crash(fake):
    fake.fail_roles.add("narrator")
    assert TestClient(app).post("/api/session", json={}).status_code == 503
