"""Terminal front-end."""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

from . import llm
from .config import PACKAGED_MODELS
from .game import Game
from .memory import get_emotions
from .story import default_story

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


def run_game(show_stats: bool = False) -> None:
    router = llm.get_router()
    problems = router.validate()
    if problems:
        print("Cannot start:\n  " + "\n  ".join(problems))
        print("\nAdd the key(s) to your .env (see .env.example), then run `varenmoor models` to check.")
        return

    game = Game(_player_id())
    print(BANNER)
    print("Type 'next' to advance stage, 'exit' to quit.\n")
    try:
        while not game.finished:
            stage = game.story.stage(game.stage)
            _stage_header(stage.id)

            if not stage.characters:  # pure narration stage
                try:
                    print(f"\n[NARRATOR]: {game.narrate_current_stage()}\n")
                except llm.AllModelsFailed as exc:
                    print(f"\n[The castle is silent. {exc}]\n")
                input("\nPress Enter to continue...")
                game.skip()
                continue

            while True:
                text = input("\nYOU: ").strip()
                if not text:
                    continue
                if text.lower() == "exit":
                    print("\nGame ended.")
                    return
                if text.lower() == "next":
                    game.skip()
                    break
                try:
                    result = game.submit(text)
                except llm.AllModelsFailed as exc:
                    print(f"\n[The castle falls silent. Try again in a moment.]\n  ({exc})")
                    continue

                if result.show_narration:
                    print(f"\n[NARRATOR]: {result.narration}\n")
                for char, line in result.responses.items():
                    print(f"\n[{char.upper()}]: {line}")
                if result.advanced:
                    print("\n[The scene shifts…]\n")
                    break
                if game.turn % 3 == 0:
                    _emotion_summary(game.player_id, stage.characters)
    finally:
        game.close()
        if show_stats:
            print("\n" + router.stats())

    print(f"\n{BANNER}\n  THE END\n{BANNER}")


def _init_config(dest: str) -> int:
    target = Path(dest)
    if target.exists():
        print(f"{target} already exists; not overwriting.")
        return 1
    shutil.copy(PACKAGED_MODELS, target)
    print(f"Wrote {target}. Edit it to change which model handles which task.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="varenmoor", description="A gothic-horror multi-agent text game.")
    parser.add_argument("-v", "--verbose", action="store_true", help="log model fallbacks and failures")
    parser.add_argument("--models", metavar="FILE", help="use this models.yaml instead of ./models.yaml")
    parser.add_argument("--stats", action="store_true", help="print LLM call counts when the game ends")
    sub = parser.add_subparsers(dest="cmd")
    p_models = sub.add_parser("models", help="show role -> model wiring and check API keys")
    p_models.add_argument("--ping", action="store_true", help="send a tiny request to every configured model")
    p_init = sub.add_parser("init-config", help="write an editable copy of models.yaml here")
    p_init.add_argument("dest", nargs="?", default="models.yaml")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.models:
        os.environ["VARENMOOR_MODELS_FILE"] = args.models

    try:
        if args.cmd == "init-config":
            sys.exit(_init_config(args.dest))
        if args.cmd == "models":
            from .diagnostics import show_models
            sys.exit(show_models(ping=args.ping))
        run_game(show_stats=args.stats)
    except llm.ConfigError as exc:
        sys.exit(f"Config error: {exc}")
    except (KeyboardInterrupt, EOFError):
        print("\n\nGame ended.")
