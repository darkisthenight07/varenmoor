"""Narrator + story orchestrator: describes the scene and decides when it ends."""
from __future__ import annotations

from ..llm import ask
from ..state import AgentState
from ..story import default_story

PROMPT = """
You are the Narrator and Story Orchestrator for Vardenmoor — a gothic horror.
You have full knowledge of the story arc and are its guardian.

FULL STORY ARC (use this to stay coherent — never let narration reference AHEAD stages):
{story_arc}

CURRENT SCENE DETAILS:
{scene}

PLAYER'S LAST ACTION: "{last_action}"

YOUR DUAL ROLE:

1. NARRATOR — Write 2-3 vivid, atmospheric sentences about what the player experiences RIGHT NOW.
   - Stay true to THIS stage's tone and content only
   - Do not invent lore that contradicts the story arc above
   - If this is the very first action in a stage, set the scene freshly
   - If the player has been here before, react to their action without repeating prior description
   - Sustain cold, dread-filled gothic atmosphere throughout

2. ORCHESTRATOR — Decide whether the story should advance to the next stage.
   Advance only when at least one of these is true:
   - The player's action meaningfully fulfills the scene's objective
   - The player explicitly moves on ("I leave", "I walk out", "I go forward")
   - The interaction has reached a natural conclusion for this scene
   NEVER advance on the very first turn of a stage (no sanitized_input yet).
   For narration-only stages (no characters), describe the scene and set ADVANCE: yes.

End your response with EXACTLY one of these lines:
ADVANCE: yes
ADVANCE: no

Return ONLY narration followed by the ADVANCE line. No tool calls, no XML, no meta-commentary.
"""

NARRATE_ONLY_PROMPT = (
    "You are the narrator. Narrate this horror scene vividly in 3-4 sentences.\n"
    "Scene: {description}"
)


def parse_narration(content: str) -> tuple[str, bool]:
    advance, lines = False, []
    for line in content.splitlines():
        if line.strip().lower().startswith("advance:"):
            advance = "yes" in line.lower()
        else:
            lines.append(line)
    return "\n".join(lines).strip(), advance


def narrator_node(state: AgentState) -> dict:
    story = default_story()
    content = ask(PROMPT.format(
        story_arc=story.arc_summary(state["stage"]),
        scene=story.scene_brief(state["stage"]),
        last_action=state.get("sanitized_input") or "[start of scene]",
    ))
    narration, advance = parse_narration(content)
    return {"narration": narration, "advance_stage": advance}


def narrate_only(stage_id: str) -> str:
    """Narration for stages with no characters (no graph run needed)."""
    return ask(NARRATE_ONLY_PROMPT.format(description=default_story().stage(stage_id).description))
