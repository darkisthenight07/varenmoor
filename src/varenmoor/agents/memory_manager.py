"""Memory manager: ONE call per NPC per turn decides emotion changes and what to remember.
(Previously two separate calls, an emotion engine and a memory system.)"""
from __future__ import annotations

import logging

from .. import llm
from ..memory import emotion, remember_relationship, remember_short, update_emotions
from ..utils import parse_json_object

log = logging.getLogger(__name__)

PROMPT = """
You are the memory manager for the character: {character}.
Given the interaction below, decide (1) how the character's emotions change and
(2) what, if anything, they will remember.

PLAYER:
{player_input}

{character} SAID:
{response}

RULES:
- Output ONLY valid JSON, no explanation, no code fences
- "emotion": integers between -5 and 5 for happiness, anger, trust (all three required)
- "short": one brief sentence summarising the exchange from the character's point of view
- "long": OPTIONAL, only for an important relationship or emotional insight:
    {{"relation": UPPERCASE_WITH_UNDERSCORES (e.g. FEARS, TRUSTS, WARNED),
      "target": string, "value": int 1-5, "context": string}}

Example:
{{
  "emotion": {{"happiness": 1, "anger": -2, "trust": 2}},
  "short": "Player asked about the wound. I avoided answering.",
  "long": {{"relation": "FEARS", "target": "player", "value": 2, "context": "hesitated when asked about death"}}
}}

Now output JSON:
"""


def _delta(data: dict) -> dict[str, int]:
    raw = data.get("emotion") if isinstance(data.get("emotion"), dict) else {}
    out = {}
    for k in emotion.EMOTIONS:
        try:
            out[k] = max(-5, min(5, int(raw.get(k, 0))))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def apply_memory_update(player_id: str, character: str, data: dict) -> None:
    update_emotions(player_id, character, _delta(data))
    if isinstance(data.get("short"), str) and data["short"].strip():
        remember_short(player_id, character, data["short"].strip()[:200])
    long = data.get("long")
    if isinstance(long, dict):
        try:
            remember_relationship(player_id, character, str(long["relation"]), str(long["target"]),
                                  int(long["value"]), str(long.get("context", ""))[:200])
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Skipping malformed long-term memory: %s", exc)


def consolidate(player_id: str, character: str, player_input: str, response: str) -> None:
    """Run the memory manager for one NPC line. Never raises: memory is best-effort."""
    try:
        data = parse_json_object(llm.ask("memory", PROMPT.format(
            character=character, player_input=player_input, response=response)))
        apply_memory_update(player_id, character, data)
    except Exception as exc:  # AllModelsFailed, malformed output, storage errors...
        log.warning("Memory update skipped for %s: %s", character, exc)
    try:  # guaranteed lightweight log of the raw interaction, no LLM needed
        remember_relationship(player_id, character, "INTERACTED_WITH", "player", 1, player_input[:120])
    except Exception as exc:
        log.warning("Interaction log failed for %s: %s", character, exc)
