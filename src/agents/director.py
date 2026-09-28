"""Conversation director: writes a tailored directive for each NPC present."""
from __future__ import annotations

from ..llm import ask
from ..state import AgentState
from ..story import default_story

PROMPT = """
You are the Conversation Director for Vardenmoor — a gothic horror game.
You write precise dialogue instructions for each NPC so their responses serve the story.

STORY ARC (orientation only — NPCs must NOT reference AHEAD stages):
{story_arc}

CURRENT SCENE: {description}
SCENE OBJECTIVE: {objective}
CHARACTERS PRESENT: {char_list}
PLAYER SAID: "{player_said}"
NARRATOR'S FRAMING: "{narration}"

For EACH character present, write a focused directive that:
- Specifies the exact emotional angle the character should take THIS turn
- Describes how the character would react to what the player just said
- Steers toward the scene objective without removing player agency
- Explicitly names what the character must NOT say or reveal this turn

GUARDRAILS to enforce in every directive:
- Characters must not reference events or people from stages they haven't encountered yet
- Characters must not acknowledge game mechanics, memory systems, or tools
- Characters must not break their established secret without story-sanctioned cause

Format STRICTLY as:
CHAR: <character name>
PROMPT: <the directive>

Repeat for each character. No other text.
"""


def parse_directives(text: str) -> dict[str, str]:
    prompts: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("char:"):
            current = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("prompt:") and current:
            prompts[current] = line.split(":", 1)[1].strip()
            current = None
    return prompts


def conversation_director_node(state: AgentState) -> dict:
    stage = default_story().stage(state["stage"])
    if not stage.characters:
        return {"dialogue_prompts": {}}

    text = ask(PROMPT.format(
        story_arc=default_story().arc_summary(stage.id),
        description=stage.description,
        objective=stage.objective,
        char_list=", ".join(stage.characters),
        player_said=state["sanitized_input"],
        narration=state.get("narration", ""),
    ))
    prompts = parse_directives(text)
    for char in stage.characters:  # fallback if the model ignored the format
        prompts.setdefault(
            char,
            f"Respond to the player's message: '{state['sanitized_input']}'. "
            f"Stay in character. Scene: {stage.description}",
        )
    return {"dialogue_prompts": prompts}
