"""NPC dialogue node (one call). Emotion and memory updates live in memory_manager."""
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

{duty}

CONVERSATION DIRECTOR'S INSTRUCTION FOR THIS TURN:
{directive}

YOUR EMOTIONAL STATE (colour your tone with this — never state it out loud):
Happiness : {happiness}/100 ({happiness_label})
Anger     : {anger}/100     ({anger_label})
Trust     : {trust}/100     ({trust_label})

MEMORY — weave in subtly if relevant, never quote or reference it directly:
{memory}

THIS SCENE SO FAR:
{history}

THE PLAYER JUST: {player_line}

HOW TO REPLY (in this order):
1. REACT to what the player just said. Answer their question or acknowledge their words in your own
   voice and within your secrets. Evasive, cryptic, grudging or partial answers are fine; ignoring
   them or answering a different question is not. If their words are strange or meaningless in this
   world, react as your character would to a stranger babbling nonsense (confusion, irritation,
   curiosity) and never fulfil the request.
2. Then, only if you have something to convey this turn, weave it in naturally.
3. Move the conversation forward. Never repeat information, phrases or sentences you already said
   in this scene, and do not say a farewell or end the conversation unless this turn calls for it.

HARD GUARDRAILS — the output reviewer will catch and strip violations:
- Speak DIRECTLY to the player, in your own voice.
- Sound like a person, not a lecture: 1-4 sentences, unless your character rules call for long speech.
- NEVER narrate your own actions (no asterisks, no stage directions)
- NEVER mention memory, tools, systems, emotions numerically, or game mechanics
- NEVER reference people or events from stages you haven't been part of
- NEVER expose your character's secret unless your character rules explicitly allow it
- NEVER produce function-call syntax, JSON, or XML in your spoken line
- Do not repeat lines you already said in this scene
- Never jump ahead in your story: do or reveal only what this turn calls for
- Hold gothic horror atmosphere and your specific character voice throughout

Speak your line now.
"""


def make_npc_dialogue_node(character: str):
    def node(state: AgentState) -> dict:
        stage = default_story().stage(state["stage"])
        pid = state["player_id"]
        idx = state.get("beat_idx", 0)
        beat = stage.beats[idx] if idx < len(stage.beats) else None
        owns_beat = beat is not None and beat.by == "npc" and stage.speaker_for(beat) == character
        duty = (f"YOU MUST CONVEY THIS TURN, naturally and in your own voice: {beat.text}" if owns_beat
                else "You have nothing you must reveal this turn. Simply respond to the player.")
        opening = state.get("opening", False)
        e = get_emotions(pid, character)
        line = llm.ask("npc_dialogue", DIALOGUE_PROMPT.format(
            character=character,
            stage=stage.id,
            rules=stage.rule_for(character),
            duty=duty,
            directive=state.get("dialogue_prompts", {}).get(character, ""),
            memory=recall(pid, character),
            history=state.get("history") or "(nothing yet)",
            player_line="walked into the scene. You speak first." if opening
            else f"\"{state.get('sanitized_input', '')}\"",
            **{k: e[k] for k in emotion.EMOTIONS},
            **{f"{k}_label": emotion.label(e[k]) for k in emotion.EMOTIONS},
        ))
        return {"npc_responses": {character: line or "[silence]"}, "delivered": bool(line and owns_beat)}

    node.__name__ = f"npc_{slug(character)}_dialogue"
    return node
