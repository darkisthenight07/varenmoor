"""Story definition: typed stage model plus a YAML loader."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ENDING = "ending"  # sentinel returned by Story.next() after the final stage
DEFAULT_OBJECTIVE = "Progress through the scene naturally."
DEFAULT_MAX_TURNS = 14
_DEFAULT_STORY = Path(__file__).parent / "data" / "vardenmoor.yaml"


@dataclass(frozen=True)
class Beat:
    """One step of a scene. Beats play strictly in order and are what moves the story on.

    by="npc"       a character conveys it in dialogue (done once they have spoken it)
    by="player"    the player has to do it (the narrator judges it from what the player says/does)
    by="narrator"  the narrator alone delivers it (nobody speaks that turn), e.g. a scene's opening
    """
    id: str
    text: str
    by: str = "player"
    hint: str = ""          # affordance the narrator may surface if the player is lost
    min_turns: int = 0      # a player beat can't complete before this many turns in the stage
    who: str = ""           # which character delivers an npc beat (default: first in the stage)


@dataclass(frozen=True)
class Stage:
    id: str
    description: str
    characters: tuple[str, ...] = ()
    rules: dict[str, str] = field(default_factory=dict)
    objective: str = DEFAULT_OBJECTIVE
    lore: str = ""                         # director-only background, never stated outright
    beats: tuple[Beat, ...] = ()           # empty = cutscene: narrated once, then the story moves on
    max_turns: int = DEFAULT_MAX_TURNS     # safety net: after this the story carries the player along

    @property
    def nudge_turns(self) -> int:
        """From this turn on, the world starts steering the player toward the current beat."""
        return max(3, self.max_turns // 2)

    def rule_for(self, character: str) -> str:
        return self.rules.get(character, "Speak in character.")

    def speaker_for(self, beat: Beat) -> str:
        return beat.who or (self.characters[0] if self.characters else "")


class Story:
    def __init__(self, title: str, stages: list[Stage]):
        if not stages:
            raise ValueError("A story needs at least one stage.")
        ids = [s.id for s in stages]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate stage ids in story definition.")
        self.title = title
        self.stages = stages
        self._by_id = {s.id: s for s in stages}

    @property
    def first(self) -> str:
        return self.stages[0].id

    @property
    def characters(self) -> list[str]:
        """Every NPC across all stages, in order of first appearance."""
        seen: list[str] = []
        for stage in self.stages:
            for char in stage.characters:
                if char not in seen:
                    seen.append(char)
        return seen

    def stage(self, stage_id: str) -> Stage:
        try:
            return self._by_id[stage_id]
        except KeyError:
            raise KeyError(f"Unknown stage '{stage_id}'. Valid: {list(self._by_id)}") from None

    def next(self, stage_id: str) -> str:
        """Id of the stage after `stage_id`, or ENDING after the last one."""
        ids = [s.id for s in self.stages]
        i = ids.index(stage_id)
        return ids[i + 1] if i + 1 < len(ids) else ENDING

    def scene_brief(self, stage_id: str) -> str:
        s = self.stage(stage_id)
        out = (
            f"Stage: {s.id}\n"
            f"Scene: {s.description}\n"
            f"Characters present: {list(s.characters) or 'none'}\n"
            f"Objective: {s.objective}"
        )
        if s.lore:
            out += f"\nDIRECTOR-ONLY LORE (colour the scene with it, never state it outright):\n{s.lore}"
        if s.rules.get("environment"):
            out += f"\nNARRATION STYLE:\n{s.rules['environment']}"
        return out

    def arc_summary(self, current: str) -> str:
        """Past/now/ahead overview so agents stay coherent without leaking spoilers."""
        ids = [s.id for s in self.stages]
        idx = ids.index(current) if current in ids else 0
        lines = [f"STORY ARC  (player is currently at: {current})\n"]
        for i, s in enumerate(self.stages):
            tag = "PAST" if i < idx else ("NOW" if i == idx else "AHEAD")
            first_line = s.description.strip().splitlines()[0]
            lines.append(f"  {tag} [{s.id}]  chars: {list(s.characters) or ['none']}  |  {first_line}")
        return "\n".join(lines)


def _beats(d: dict, characters: tuple[str, ...], objective: str) -> tuple[Beat, ...]:
    raw = d.get("beats")
    if raw is None:  # older stories: one player beat built from the objective (cutscene if no characters)
        return (Beat("objective", objective, "player"),) if characters else ()
    beats, seen = [], set()
    for b in raw:
        beat = Beat(id=str(b["id"]), text=str(b["text"]).strip(), by=b.get("by", "player"),
                    hint=str(b.get("hint", "")).strip(), min_turns=int(b.get("min_turns", 0)),
                    who=str(b.get("who", "")))
        if beat.by not in ("npc", "player", "narrator"):
            raise ValueError(f"Stage '{d['id']}' beat '{beat.id}': 'by' must be npc, player or narrator, "
                             f"got '{beat.by}'.")
        if beat.by == "npc" and not (beat.who or characters):
            raise ValueError(f"Stage '{d['id']}' beat '{beat.id}' is an npc beat but the stage has no characters.")
        if beat.who and beat.who not in characters:
            raise ValueError(f"Stage '{d['id']}' beat '{beat.id}': '{beat.who}' is not a character in this stage.")
        if beat.id in seen:
            raise ValueError(f"Stage '{d['id']}' has duplicate beat id '{beat.id}'.")
        seen.add(beat.id)
        beats.append(beat)
    return tuple(beats)


def load_story(path: str | Path | None = None) -> Story:
    raw = yaml.safe_load(Path(path or _DEFAULT_STORY).read_text(encoding="utf-8"))
    stages = []
    for d in raw["stages"]:
        characters = tuple(d.get("characters") or ())
        objective = d.get("objective") or DEFAULT_OBJECTIVE
        stages.append(Stage(
            id=d["id"],
            description=d["description"].strip(),
            characters=characters,
            rules={k: v.strip() for k, v in (d.get("rules") or {}).items()},
            objective=objective,
            lore=(d.get("lore") or "").strip(),
            beats=_beats(d, characters, objective),
            max_turns=int(d.get("max_turns", DEFAULT_MAX_TURNS)),
        ))
    return Story(raw.get("title", "Untitled"), stages)


@lru_cache(maxsize=1)
def default_story() -> Story:
    return load_story()
