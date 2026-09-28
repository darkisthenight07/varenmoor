"""Story definition: typed stage model plus a YAML loader."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ENDING = "ending"  # sentinel returned by Story.next() after the final stage
DEFAULT_OBJECTIVE = "Progress through the scene naturally."
_DEFAULT_STORY = Path(__file__).parent / "data" / "vardenmoor.yaml"


@dataclass(frozen=True)
class Stage:
    id: str
    description: str
    characters: tuple[str, ...] = ()
    rules: dict[str, str] = field(default_factory=dict)
    objective: str = DEFAULT_OBJECTIVE

    def rule_for(self, character: str) -> str:
        return self.rules.get(character, "Speak in character.")


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
        return (
            f"Stage: {s.id}\n"
            f"Scene: {s.description}\n"
            f"Characters present: {list(s.characters) or 'none'}\n"
            f"Objective: {s.objective}"
        )

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


def load_story(path: str | Path | None = None) -> Story:
    raw = yaml.safe_load(Path(path or _DEFAULT_STORY).read_text(encoding="utf-8"))
    stages = [
        Stage(
            id=d["id"],
            description=d["description"].strip(),
            characters=tuple(d.get("characters") or ()),
            rules={k: v.strip() for k, v in (d.get("rules") or {}).items()},
            objective=d.get("objective") or DEFAULT_OBJECTIVE,
        )
        for d in raw["stages"]
    ]
    return Story(raw.get("title", "Untitled"), stages)


@lru_cache(maxsize=1)
def default_story() -> Story:
    return load_story()
