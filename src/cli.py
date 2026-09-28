"""Terminal game loop."""
from __future__ import annotations

import logging
import re
import uuid

from .agents import narrate_only
from .graph import build_agent
from .memory import get_emotions, long_term
from .state import initial_state
from .story import ENDING, default_story

BANNER = "=" * 50


def _player_id() -> str:
    print("Enter your player name (or press Enter for a new anonymous session):")
    raw = input("  > ").strip()
    if raw:
        pid = re.sub(r"[^a-z0-9_-]", "_", raw.lower())
        print(f"\nWelcome, {raw}. Your session ID: {pid}\n")
        return pid
    pid = uuid.uuid4().hex[:8]
    print(f"\nAnonymous session started. ID: {pid}\n")
    return pid


def _stage_header(stage_id: str) -> None:
    print(f"\n{'─' * 50}\n  STAGE: {stage_id.upper()}\n{'─' * 50}")
    print(f"\n{default_story().stage(stage_id).description}\n")


def _emotion_summary(pid: str, chars) -> None:
    print("\n  [Emotional State]")
    for c in chars:
        e = get_emotions(pid, c)
        print(f"  {c}: happiness={e['happiness']} anger={e['anger']} trust={e['trust']}")


def run_game() -> None:
    story = default_story()
    agent = build_agent(story)
    pid = _player_id()
    stage, turn = story.first, 0

    print(BANNER)
    print("Type 'next' to advance stage, 'exit' to quit.\n")

    try:
        while stage != ENDING:
            current = story.stage(stage)
            _stage_header(stage)

            if not current.characters:  # pure narration stage
                print(f"\n[NARRATOR]: {narrate_only(stage)}\n")
                input("\nPress Enter to continue...")
                stage, turn = story.next(stage), 0
                continue

            while True:
                text = input("\nYOU: ").strip()
                if not text:
                    continue
                if text.lower() == "exit":
                    print("\nGame ended.")
                    return
                if text.lower() == "next":
                    stage, turn = story.next(stage), 0
                    break

                turn += 1
                out = agent.invoke(initial_state(pid, stage, text))
                narration = (out.get("narration") or "").strip()
                final = out.get("final_responses") or {}

                if narration and (turn == 1 or out.get("advance_stage") or not final):
                    print(f"\n[NARRATOR]: {narration}\n")
                for char, line in final.items():
                    print(f"\n[{char.upper()}]: {line}")

                if out.get("advance_stage"):
                    print("\n[The scene shifts…]\n")
                    stage, turn = story.next(stage), 0
                    break
                if turn % 3 == 0:
                    _emotion_summary(pid, current.characters)
    finally:
        long_term.close()

    print(f"\n{BANNER}\n  THE END\n{BANNER}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        run_game()
    except (KeyboardInterrupt, EOFError):
        print("\n\nGame ended.")
