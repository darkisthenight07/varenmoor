"""Game session: owns the story position, drives scenes and runs memory updates in the background.

Story progression is beat-driven: each stage has an ordered plan of beats (things a character says
or the player does). When the last beat is done the game moves on by itself and opens the next
scene, so the player never has to skip anything."""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from . import llm
from .agents import SILENT, consolidate
from .graph import build_agent
from .memory import long_term
from .state import initial_state
from .story import ENDING, Story, default_story

log = logging.getLogger(__name__)

HISTORY_LINES = 8     # recent lines shown to the narrator and NPCs
CARRY_LINES = 3       # lines of the previous scene the narrator may bridge from


@dataclass
class Event:
    """One thing the player sees. kind: "narration" | "say" | "end"."""
    kind: str
    text: str = ""
    speaker: str = ""


class Game:
    def __init__(self, player_id: str, *, story: Story | None = None, agent=None):
        self.player_id = player_id
        self.story = story or default_story()
        self.agent = agent or build_agent(self.story)
        self.stage = self.story.first
        self.turn = 0                 # player turns played in the current stage
        self.beat_idx = 0             # current beat of the current stage
        self._history: list[str] = []
        self._carry = ""
        self._needs_open = True       # the current scene has not been opened yet
        self._pool: ThreadPoolExecutor | None = None
        self._pending: list[Future] = []

    @property
    def finished(self) -> bool:
        return self.stage == ENDING

    @property
    def needs_open(self) -> bool:
        return self._needs_open and not self.finished

    # ── background memory ─────────────────────────────────────────────────
    def _background(self) -> bool:
        return llm.pipeline().background_memory

    def wait_for_memory(self) -> None:
        """Block until the previous turn's memory update has landed (usually instant)."""
        for fut in self._pending:
            fut.result()
        self._pending.clear()

    def _consolidate(self, sanitized: str, final: dict[str, str]) -> None:
        if llm.pipeline().skip_memory_on_silence and sanitized == SILENT:
            return
        for char, line in final.items():
            if not line or line == "[silence]":
                continue
            if self._background():
                self._pool = self._pool or ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory")
                self._pending.append(self._pool.submit(consolidate, self.player_id, char, sanitized, line))
            else:
                consolidate(self.player_id, char, sanitized, line)

    # ── scene bookkeeping ─────────────────────────────────────────────────
    def _invoke(self, text: str, opening: bool) -> dict:
        return self.agent.invoke(initial_state(
            self.player_id, self.stage, text, opening=opening,
            history="\n".join(self._history[-HISTORY_LINES:]),
            carryover=self._carry if opening else "",
            beat_idx=self.beat_idx, turns_in_stage=self.turn))

    @staticmethod
    def _events(out: dict) -> list[Event]:
        events = []
        narration = (out.get("narration") or "").strip()
        if narration:
            events.append(Event("narration", narration))
        for char, line in (out.get("final_responses") or {}).items():
            if line and line != "[silence]":
                events.append(Event("say", line, char))
        return events

    def _record(self, player_text: str, events: list[Event]) -> None:
        if player_text:
            self._history.append("PLAYER: " + ("(says nothing)" if player_text == SILENT else player_text[:200]))
        for e in events:
            self._history.append(f"NARRATOR: {e.text[:200]}" if e.kind == "narration"
                                 else f"{e.speaker.upper()}: {e.text[:300]}")
        del self._history[:-12]

    def _advance_beats(self, out: dict) -> bool:
        """Update the beat pointer after a turn. True when the stage's plan is complete."""
        idx = out.get("beat_idx", self.beat_idx) + (1 if out.get("delivered") else 0)
        self.beat_idx = idx
        return idx >= len(self.story.stage(self.stage).beats)

    def _enter_next(self) -> None:
        self._carry = "\n".join(self._history[-CARRY_LINES:])
        self._history = []
        self.stage = self.story.next(self.stage)
        self.turn = self.beat_idx = 0
        self._needs_open = not self.finished

    def _open_scene(self, events: list[Event]) -> None:
        """Open the current scene and keep going through cutscenes until the player must act.
        Appends to `events` as it goes so a mid-chain outage keeps what was already produced."""
        while not self.finished:
            self._needs_open = True
            out = self._invoke("", opening=True)          # may raise llm.AllModelsFailed
            opened = self._events(out)
            events.extend(opened)
            self._record("", opened)
            self._needs_open = False
            if not self._advance_beats(out):
                return
            self._enter_next()
        events.append(Event("end"))

    # ── public API ────────────────────────────────────────────────────────
    def start(self) -> list[Event]:
        """Open the current scene (call once at the beginning, and again after an outage)."""
        events: list[Event] = []
        try:
            self._open_scene(events)
        except llm.AllModelsFailed:
            if not events:
                raise
        return events

    def submit(self, text: str) -> list[Event]:
        """Play one player turn and return what the player sees, including the next scene's
        opening if this turn finished the scene. May raise llm.AllModelsFailed (state unchanged)."""
        if self.finished:
            return [Event("end")]
        if self._needs_open:                  # an earlier outage left the scene unopened
            return self.start()
        self.wait_for_memory()
        out = self._invoke(text, opening=False)
        self.turn += 1
        events = self._events(out)
        sanitized = out.get("sanitized_input", "")
        self._record(sanitized, events)
        self._consolidate(sanitized, out.get("final_responses") or {})
        if self._advance_beats(out):
            self._enter_next()
            try:
                self._open_scene(events)
            except llm.AllModelsFailed as exc:
                log.warning("Next scene could not open yet: %s", exc)
        return events

    def skip(self) -> str:
        """Developer shortcut (`--dev`): jump to the next stage. The scene opens on the next start()."""
        self._enter_next()
        return self.stage

    def close(self) -> None:
        try:
            self.wait_for_memory()
        finally:
            if self._pool:
                self._pool.shutdown(wait=True)
            long_term.close()
