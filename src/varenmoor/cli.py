"""Terminal front-end."""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import textwrap
import uuid
from pathlib import Path

from . import llm
from .config import PACKAGED_MODELS
from .game import Event, Game

BANNER = "=" * 50
_COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")
_DIM, _BOLD, _OFF = ("\033[3;90m", "\033[1m", "\033[0m") if _COLOR else ("", "", "")


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


def _display_name(char: str) -> str:
    return "The " + char.replace("_", " ").title() if char != "doctor" else "The Doctor"


def show(events: list[Event]) -> None:
    """Print what the player sees: narration in dim italics, then each character's line."""
    width = min(shutil.get_terminal_size((80, 20)).columns, 88) - 2
    for e in events:
        if e.kind == "narration":
            print("\n" + _DIM + textwrap.fill(e.text, width) + _OFF)
        elif e.kind == "say":
            print(f"\n{_BOLD}{_display_name(e.speaker)}:{_OFF} " + textwrap.fill(
                e.text, width, subsequent_indent="  "))
        elif e.kind == "end":
            print(f"\n{BANNER}\n  THE END\n{BANNER}")


def run_game(show_stats: bool = False, dev: bool = False) -> None:
    router = llm.get_router()
    problems = router.validate()
    if problems:
        print("Cannot start:\n  " + "\n  ".join(problems))
        print("\nAdd the key(s) to your .env (see .env.example), then run `varenmoor models` to check.")
        return

    game = Game(_player_id())
    print(BANNER)
    print("Say or do whatever you like. The story moves on as you talk and act.")
    print("Type 'exit' to quit." + ("  [dev: '/skip' jumps to the next scene]" if dev else "") + "\n" + BANNER)
    try:
        while not game.finished:
            try:
                if game.needs_open:
                    show(game.start())
                    continue
            except llm.AllModelsFailed as exc:
                print(f"\n[The castle stirs slowly. Press Enter to try again.]\n  ({exc})")
                input()
                continue
            text = input("\n> ").strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                print("\nGame ended.")
                return
            if dev and text.lower() == "/skip":
                game.skip()
                continue
            try:
                show(game.submit(text))
            except llm.AllModelsFailed as exc:
                print(f"\n[The castle falls silent. Try again in a moment.]\n  ({exc})")
    finally:
        game.close()
        if show_stats:
            print("\n" + router.stats())


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
    parser.add_argument("--dev", action="store_true", help="enable developer commands (/skip)")
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
        run_game(show_stats=args.stats, dev=args.dev)
    except llm.ConfigError as exc:
        sys.exit(f"Config error: {exc}")
    except (KeyboardInterrupt, EOFError):
        print("\n\nGame ended.")
