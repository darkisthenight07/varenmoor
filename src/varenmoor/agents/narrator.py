"""Scene agent: ONE call that narrates, judges whether the player completed the current beat,
and briefs each NPC. Story progression is driven by the stage's beats (see story/loader.py), so
scenes end because something happened in them, never because the player typed a skip command."""
from __future__ import annotations

import re

from .. import llm
from ..state import AgentState
from ..story import Beat, Stage, default_story

PROMPT = """
You are the Narrator and Director of Vardenmoor, a gothic horror text game. You guard the story
and pace it so that it unfolds naturally from what the player says and does. The player never
sees this brief.

FULL STORY ARC (never reference AHEAD stages):
{story_arc}

CURRENT SCENE:
{scene}

SCENE PLAN (beats play strictly in order):
{plan}

{beat_brief}

{carry}RECENT EVENTS IN THIS SCENE:
{history}

CHARACTERS PRESENT: {char_list}
PLAYER'S LAST ACTION: "{last_action}"

YOUR THREE JOBS:

1. NARRATE. Write 2-4 vivid, atmospheric sentences, in second person, ONLY when:
   - the scene is opening (set it freshly and bridge naturally from the previous scene), or
   - the player does something physical, moves, or looks at something, or
   - a beat completes (show its consequence).
   When the player is simply talking, write NARRATION: none. The characters' words carry the scene.
   Never repeat earlier narration. Never invent lore that contradicts the arc.

2. JUDGE. If the current beat belongs to the player, decide whether their last action clearly
   accomplishes it. Be generous: short, casual or slangy phrasing counts ("leave", "ok bye",
   "I go", "I tie him down"), and so does a clear statement of intent. Answer no only when the
   player has not really done or tried it. Do not be gullible about unrelated chatter.

3. DIRECT. For EACH character present, write a short directive: the emotional angle for THIS
   turn, how they react to what the player just said, and what they must NOT reveal. Characters
   never reference stages they have not been part of, game mechanics, or memory systems.

Format STRICTLY, with no other text, no XML, no commentary:
NARRATION: <2-4 sentences, or none>
BEAT_DONE: yes|no
CHAR: <character name>
PROMPT: <that character's directive>
(repeat CHAR / PROMPT for each character present)
"""

_KEY = re.compile(r"^\s*(NARRATION|BEAT_DONE|ADVANCE|CHAR|PROMPT)\s*:\s*(.*)$", re.IGNORECASE)
_NOTHING = {"none", "n/a", "na", "-", "—", "[none]", "(none)", "nothing"}


def parse_scene(text: str, characters: tuple[str, ...] | list[str] = ()) -> tuple[str, bool, dict[str, str]]:
    """Parse the scene agent's output into (narration, beat_done, {char: directive}).
    Tolerates multi-line values, odd casing, a missing NARRATION label, and the old ADVANCE key."""
    narration: list[str] = []
    prompts: dict[str, str] = {}
    done = False
    section: str | None = None
    current_char: str | None = None
    for line in text.splitlines():
        m = _KEY.match(line)
        if m:
            key, val = m.group(1).upper(), m.group(2).strip()
            if key == "NARRATION":
                section = "narration"
                if val:
                    narration.append(val)
            elif key in ("BEAT_DONE", "ADVANCE"):
                done = val.lower().startswith("y")
                section = None
            elif key == "CHAR":
                current_char, section = val.lower(), "char"
            elif key == "PROMPT" and current_char:
                prompts[current_char] = val
                section = "prompt"
            continue
        if section == "narration" and line.strip():
            narration.append(line.strip())
        elif section == "prompt" and current_char and line.strip():
            prompts[current_char] = (prompts[current_char] + " " + line.strip()).strip()
        elif section is None and not narration and not prompts and line.strip():
            narration.append(line.strip())  # unlabeled leading text is the narration
    joined = " ".join(narration).strip()
    return ("" if joined.lower().strip(".") in _NOTHING else joined), done, prompts


def render_plan(stage: Stage, idx: int) -> str:
    if not stage.beats:
        return "  (no beats: this is a cutscene. Narrate it once, vividly; the story then moves on by itself.)"
    rows = []
    for i, b in enumerate(stage.beats):
        mark = "DONE " if i < idx else "NOW  " if i == idx else "LATER"
        rows.append(f"  {mark} [{b.by}] {b.text}")
    return "\n".join(rows)


def beat_brief(stage: Stage, idx: int, turn_no: int, opening: bool, nudge: bool, force: bool) -> str:
    """What the narrator must know about the beat in play, including pacing pressure."""
    if idx >= len(stage.beats):
        return "CURRENT BEAT: none."
    b: Beat = stage.beats[idx]
    if b.by == "npc":
        who = stage.speaker_for(b)
        return (f"CURRENT BEAT: {who} conveys it in dialogue this turn: {b.text}\n"
                f"Write BEAT_DONE: no (it is not the player's to complete) and make {who}'s directive deliver it "
                f"naturally, in one go, in the character's voice.")
    out = f"CURRENT BEAT (the PLAYER must do this): {b.text}"
    if opening:
        return out + "\nThe scene is only opening, so write BEAT_DONE: no."
    if turn_no < b.min_turns:
        out += (f"\nIt is too early to complete this (turn {turn_no} of at least {b.min_turns}). "
                f"Write BEAT_DONE: no and let the scene hold the player a little longer.")
    if force:
        out += ("\nFORCE: the player has lingered too long. Narrate this beat happening naturally "
                "(they are carried along by events) and write BEAT_DONE: yes.")
    elif nudge:
        hint = f" Surface this in your narration or a character's directive: {b.hint}" if b.hint else ""
        out += ("\nThe scene is dragging. Without breaking immersion, make the world and the characters "
                f"steer the player toward the beat.{hint}")
    return out


def scene_node(state: AgentState) -> dict:
    story = default_story()
    stage = story.stage(state["stage"])
    idx = state.get("beat_idx", 0)
    opening = state.get("opening", False)
    turn_no = state.get("turns_in_stage", 0) + (0 if opening else 1)   # this turn's number, 1-based
    current = stage.beats[idx] if idx < len(stage.beats) else None
    on_player_beat = current is not None and current.by == "player" and not opening
    force = on_player_beat and turn_no > stage.max_turns
    nudge = on_player_beat and turn_no >= stage.nudge_turns

    carry = state.get("carryover", "")
    text = llm.ask("narrator", PROMPT.format(
        story_arc=story.arc_summary(stage.id),
        scene=story.scene_brief(stage.id),
        plan=render_plan(stage, idx),
        beat_brief=beat_brief(stage, idx, turn_no, opening, nudge, force),
        carry=f"JUST BEFORE (previous scene, for bridging only):\n{carry}\n\n" if opening and carry else "",
        history=state.get("history") or "(nothing yet)",
        char_list=", ".join(stage.characters) or "none",
        last_action="[the player has just arrived in this scene]" if opening
        else (state.get("sanitized_input") or "[no action]"),
    ))
    narration, judged, prompts = parse_scene(text, stage.characters)

    beat_done = bool(on_player_beat and (force or (judged and turn_no >= current.min_turns)))
    if beat_done:
        idx += 1
    if (opening or beat_done) and not narration:
        narration = stage.description if opening else ""

    for char in stage.characters:  # fallback if the model skipped a directive
        prompts.setdefault(char, "React naturally to the player, in character.")
    return {"narration": narration, "beat_done": beat_done, "beat_idx": idx, "dialogue_prompts": prompts}
