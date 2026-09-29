"""Game session: owns stage progression and runs memory updates in the background."""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from . import llm
from .agents import SILENT, consolidate, narrate_only
from .graph import build_agent
from .memory import long_term
from .state import initial_state
from .story import ENDING, Story, default_story

log = logging.getLogger(__name__)


@dataclass
class TurnResult:
    stage: str                       # stage this turn was played in
    narration: str = ""
    responses: dict[str, str] = field(default_factory=dict)
    advanced: bool = False
    next_stage: str = ""
    show_narration: bool = False


class Game:
    def __init__(self, player_id: str, *, story: Story | None = None, agent=None):
        self.player_id = player_id
        self.story = story or default_story()
        self.agent = agent or build_agent(self.story)
        self.stage = self.story.first
        self.turn = 0
        self._pool: ThreadPoolExecutor | None = None
        self._pending: list[Future] = []

    @property
    def finished(self) -> bool:
        return self.stage == ENDING

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

    # ── turns ─────────────────────────────────────────────────────────────
    def submit(self, text: str) -> TurnResult:
        """Play one player turn. May raise llm.AllModelsFailed (state is left unchanged)."""
        self.wait_for_memory()
        stage = self.stage
        out = self.agent.invoke(initial_state(self.player_id, stage, text))
        self.turn += 1
        narration = (out.get("narration") or "").strip()
        final = out.get("final_responses") or {}
        advanced = bool(out.get("advance_stage"))
        result = TurnResult(
            stage=stage, narration=narration, responses=dict(final), advanced=advanced,
            show_narration=bool(narration) and (self.turn == 1 or advanced or not final),
        )
        self._consolidate(out.get("sanitized_input", ""), final)
        if advanced:
            self.skip()
        result.next_stage = self.stage
        return result

    def skip(self) -> str:
        """Move to the next stage (also used for the player's `next` command)."""
        self.stage, self.turn = self.story.next(self.stage), 0
        return self.stage

    def narrate_current_stage(self) -> str:
        """Narration for a stage without characters."""
        return narrate_only(self.stage)

    def close(self) -> None:
        try:
            self.wait_for_memory()
        finally:
            if self._pool:
                self._pool.shutdown(wait=True)
            long_term.close()
