"""NPC dialogue node (one call). Emotion and memory updates now live in memory_manager."""
from __future__ import annotations

from .. import llm
from ..memory import emotion, get_emotions, recall
from ..state import AgentState
from ..story import default_story
from ..utils import slug

DIALOGUE_PROMPT = """
You are {character} inside Vardenmoor, a cursed gothic castle.
CURRENT STAGE: {stage}

YOUR CHARACTER RULES (core identity — never break these):
{rules}

CONVERSATION DIRECTOR'S INSTRUCTION FOR THIS TURN:
{directive}

YOUR EMOTIONAL STATE (colour your tone with this — never state it out loud):
Happiness : {happiness}/100 ({happiness_label})
Anger     : {anger}/100     ({anger_label})
Trust     : {trust}/100     ({trust_label})

MEMORY — weave in subtly if relevant, never quote or reference it directly:
{memory}

HARD GUARDRAILS — the output reviewer will catch and strip violations:
- Speak DIRECTLY to the player.
- NEVER narrate your own actions (no asterisks, no stage directions)
- NEVER mention memory, tools, systems, emotions numerically, or game mechanics
- NEVER reference people or events from stages you haven't been part of
- NEVER expose your character's secret unless your character rules explicitly allow it
- NEVER produce function-call syntax, JSON, or XML in your spoken line
- Hold gothic horror atmosphere and your specific character voice throughout

Speak your line now.
"""


def make_npc_dialogue_node(character: str):
    def node(state: AgentState) -> dict:
        stage = default_story().stage(state["stage"])
        pid = state["player_id"]
        e = get_emotions(pid, character)
        line = llm.ask("npc_dialogue", DIALOGUE_PROMPT.format(
            character=character,
            stage=stage.id,
            rules=stage.rule_for(character),
            directive=state.get("dialogue_prompts", {}).get(character, ""),
            memory=recall(pid, character),
            **{k: e[k] for k in emotion.EMOTIONS},
            **{f"{k}_label": emotion.label(e[k]) for k in emotion.EMOTIONS},
        ))
        return {"npc_responses": {character: line or "[silence]"}}

    node.__name__ = f"npc_{slug(character)}_dialogue"
    return node
