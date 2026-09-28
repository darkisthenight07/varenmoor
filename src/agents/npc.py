"""Per-character pipeline nodes: dialogue -> emotion update -> memory update."""
from __future__ import annotations

import json
import logging

from ..llm import ask
from ..memory import (emotion, get_emotions, recall, remember_relationship,
                      remember_short, update_emotions)
from ..state import AgentState
from ..story import default_story
from ..utils import parse_json_object, slug

log = logging.getLogger(__name__)

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

EMOTION_PROMPT = """
You are an emotion engine for the character: {character}.

Based on the interaction below, decide how the character's emotions should change.

PLAYER INPUT:
{player_input}

NPC RESPONSE:
{response}

EMOTIONS:
- happiness
- anger
- trust

RULES:
- Output ONLY valid JSON
- No explanation, no text
- Values must be integers between -5 and 5
- Include all three fields

Example:
{{"happiness": 1, "anger": -2, "trust": 2}}

Now output JSON:
"""

MEMORY_PROMPT = """
You are a memory system for character: {character}.

Decide what should be stored from this interaction.

PLAYER:
{player_input}

NPC:
{response}

MEMORY TYPES:
1. short → brief interaction summary
2. long → important relationship or emotional insight

RULES:
- Output ONLY valid JSON
- No explanation
- Can include:
  - "short": string
  - "long": {{
        "relation": string (UPPERCASE_WITH_UNDERSCORES, e.g. FEARS, TRUSTS, WARNED),
        "target": string,
        "value": int (1-5),
        "context": string
    }}

Example:
{{
  "short": "Player asked about the wound. I avoided answering.",
  "long": {{
    "relation": "FEARS",
    "target": "player",
    "value": 2,
    "context": "hesitated when asked about death"
  }}
}}

Now output JSON:
"""


def make_npc_dialogue_node(character: str):
    def node(state: AgentState) -> dict:
        stage = default_story().stage(state["stage"])
        pid = state["player_id"]
        e = get_emotions(pid, character)
        line = ask(DIALOGUE_PROMPT.format(
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


def make_npc_emotion_node(character: str):
    def node(state: AgentState) -> dict:
        raw = ask(EMOTION_PROMPT.format(
            character=character,
            player_input=state["sanitized_input"],
            response=state["npc_responses"][character],
        ))
        data = parse_json_object(raw)
        delta = {}
        for k in emotion.EMOTIONS:
            try:
                delta[k] = max(-5, min(5, int(data.get(k, 0))))
            except (TypeError, ValueError):
                delta[k] = 0
        update_emotions(state["player_id"], character, delta)
        return {}

    node.__name__ = f"npc_{slug(character)}_emotion"
    return node


def make_npc_memory_node(character: str):
    def node(state: AgentState) -> dict:
        pid = state["player_id"]
        player_input = state["sanitized_input"]
        data = parse_json_object(ask(MEMORY_PROMPT.format(
            character=character,
            player_input=player_input,
            response=state["npc_responses"][character],
        )))

        if isinstance(data.get("short"), str) and data["short"].strip():
            remember_short(pid, character, data["short"][:200])

        long = data.get("long")
        if isinstance(long, dict):
            try:
                remember_relationship(
                    pid, character, str(long["relation"]), str(long["target"]),
                    int(long["value"]), str(long.get("context", ""))[:200],
                )
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Skipping malformed long-term memory %s: %s", json.dumps(long)[:120], exc)

        # Guaranteed lightweight log of the raw interaction
        remember_relationship(pid, character, "INTERACTED_WITH", "player", 1, player_input[:120])
        return {}

    node.__name__ = f"npc_{slug(character)}_memory"
    return node
