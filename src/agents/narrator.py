"""Scene agent: one call that narrates, decides whether the story advances, and briefs each NPC.
(Previously two sequential calls, narrator then director.)"""
from __future__ import annotations

import re

from .. import llm
from ..state import AgentState
from ..story import default_story

PROMPT = """
You are the Narrator, Story Orchestrator and Conversation Director for Vardenmoor — a gothic horror.
You have full knowledge of the story arc and are its guardian.

FULL STORY ARC (use this to stay coherent — never reference AHEAD stages):
{story_arc}

CURRENT SCENE DETAILS:
{scene}

CHARACTERS PRESENT: {char_list}
PLAYER'S LAST ACTION: "{last_action}"

YOUR THREE JOBS:

1. NARRATE — Write 2-3 vivid, atmospheric sentences about what the player experiences RIGHT NOW.
   - Stay true to THIS stage's tone and content only
   - Do not invent lore that contradicts the story arc above
   - If this is the very first action in a stage, set the scene freshly
   - If the player has been here before, react to their action without repeating prior description
   - Sustain cold, dread-filled gothic atmosphere throughout

2. ORCHESTRATE — Decide whether the story should advance to the next stage.
   Advance only when at least one of these is true:
   - The player's action meaningfully fulfills the scene's objective
   - The player explicitly moves on ("I leave", "I walk out", "I go forward")
   - The interaction has reached a natural conclusion for this scene
   NEVER advance on the very first turn of a stage (no player action yet).
   For narration-only stages (no characters), describe the scene and set ADVANCE: yes.

3. DIRECT — For EACH character present, write a focused directive that:
   - Specifies the exact emotional angle the character should take THIS turn
   - Describes how the character would react to what the player just said
   - Steers toward the scene objective ({objective}) without removing player agency
   - Explicitly names what the character must NOT say or reveal this turn
   Guardrails for every directive: characters must not reference events or people from stages
   they haven't encountered yet; must not acknowledge game mechanics, memory systems, or tools;
   must not break their established secret without story-sanctioned cause.

Format STRICTLY as follows, with no other text, no XML, no meta-commentary:
NARRATION: <2-3 sentences>
ADVANCE: yes|no
CHAR: <character name>
PROMPT: <that character's directive>
(repeat CHAR / PROMPT for each character present)
"""

NARRATE_ONLY_PROMPT = (
    "You are the narrator. Narrate this horror scene vividly in 3-4 sentences.\n"
    "Scene: {description}"
)

_KEY = re.compile(r"^\s*(NARRATION|ADVANCE|CHAR|PROMPT)\s*:\s*(.*)$", re.IGNORECASE)


def parse_scene(text: str, characters: tuple[str, ...] | list[str] = ()) -> tuple[str, bool, dict[str, str]]:
    """Parse the scene agent's output into (narration, advance, {char: directive}).
    Tolerates multi-line values, odd casing, and a missing NARRATION label."""
    narration: list[str] = []
    prompts: dict[str, str] = {}
    advance = False
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
            elif key == "ADVANCE":
                advance = val.lower().startswith("y")
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
    return " ".join(narration).strip(), advance, prompts


def scene_node(state: AgentState) -> dict:
    story = default_story()
    stage = story.stage(state["stage"])
    text = llm.ask("narrator", PROMPT.format(
        story_arc=story.arc_summary(stage.id),
        scene=story.scene_brief(stage.id),
        char_list=", ".join(stage.characters) or "none",
        last_action=state.get("sanitized_input") or "[start of scene]",
        objective=stage.objective,
    ))
    narration, advance, prompts = parse_scene(text, stage.characters)
    for char in stage.characters:  # fallback if the model skipped a directive
        prompts.setdefault(
            char,
            f"Respond to the player's message: '{state.get('sanitized_input', '')}'. "
            f"Stay in character. Scene: {stage.description}",
        )
    return {"narration": narration, "advance_stage": advance, "dialogue_prompts": prompts}


def narrate_only(stage_id: str) -> str:
    """Narration for stages with no characters (no graph run needed)."""
    return llm.ask("narrator", NARRATE_ONLY_PROMPT.format(description=default_story().stage(stage_id).description))
