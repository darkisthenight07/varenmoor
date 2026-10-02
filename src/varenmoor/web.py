"""HTTP API for Varenmoor (deployed on Render). The static UI in /web talks to this."""
from __future__ import annotations

import os
import re
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import llm
from .game import Game
from .story import default_story

MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "200"))
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "3600"))

app = FastAPI(title="Varenmoor")
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


class NewSession(BaseModel):
    player: str = ""


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _purge() -> None:
    now = time.time()
    for sid in [s for s, v in _sessions.items() if now - v["seen"] > SESSION_TTL]:
        _sessions.pop(sid)["game"].close()
    while len(_sessions) >= MAX_SESSIONS:
        oldest = min(_sessions, key=lambda s: _sessions[s]["seen"])
        _sessions.pop(oldest)["game"].close()


def _get(sid: str) -> dict:
    s = _sessions.get(sid)
    if not s:
        raise HTTPException(404, "Unknown or expired session")
    s["seen"] = time.time()
    return s


def _wire(events) -> list[dict]:
    return [{"kind": e.kind, "text": e.text, "speaker": e.speaker.replace("_", " ")} for e in events]


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/session")
def new_session(body: NewSession) -> dict:
    problems = llm.get_router().validate()
    if problems:
        raise HTTPException(503, "Server not configured: " + "; ".join(problems))
    pid = re.sub(r"[^a-z0-9_-]", "_", body.player.lower())[:32] or uuid.uuid4().hex[:8]
    sid = uuid.uuid4().hex
    game = Game(pid, story=default_story())
    with _lock:
        _purge()
        _sessions[sid] = {"game": game, "seen": time.time(), "lock": threading.Lock()}
    try:
        events = game.start()
    except llm.AllModelsFailed as exc:
        _sessions.pop(sid, None)
        raise HTTPException(503, f"The castle is not answering yet. Try again shortly. ({exc})")
    return {"session_id": sid, "title": game.story.title, "events": _wire(events)}


@app.post("/api/session/{sid}/message")
def message(sid: str, body: Message) -> dict:
    s = _get(sid)
    game: Game = s["game"]
    with s["lock"]:
        try:
            events = game.submit(body.text.strip())
        except llm.AllModelsFailed as exc:
            raise HTTPException(503, f"The castle falls silent. Try again shortly. ({exc})")
    return {"events": _wire(events), "finished": game.finished}
