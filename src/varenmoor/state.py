"""LangGraph agent state."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    player_id: str
    stage: str
    player_input: str
    sanitized_input: str                        # after input review
    opening: bool                               # True when the scene is just starting (no player input)
    history: str                                # recent lines of THIS scene (what NPCs may know)
    carryover: str                              # tail of the previous scene (narrator only, for bridging)
    beat_idx: int                               # index of the current beat in the stage's plan
    turns_in_stage: int                         # player turns already played in this stage
    narration: str
    beat_done: bool                             # the player completed the current player beat this turn
    dialogue_prompts: dict[str, str]            # char -> director's directive
    npc_responses: Annotated[dict, operator.or_]  # char -> raw line (merged across parallel NPCs)
    delivered: Annotated[bool, operator.or_]    # an NPC conveyed the current npc beat this turn
    final_responses: dict[str, str]             # char -> reviewed line


def initial_state(player_id: str, stage: str, player_input: str, *, opening: bool = False,
                  history: str = "", carryover: str = "", beat_idx: int = 0,
                  turns_in_stage: int = 0) -> AgentState:
    return {
        "player_id": player_id,
        "stage": stage,
        "player_input": player_input,
        "sanitized_input": "",
        "opening": opening,
        "history": history,
        "carryover": carryover,
        "beat_idx": beat_idx,
        "turns_in_stage": turns_in_stage,
        "narration": "",
        "beat_done": False,
        "dialogue_prompts": {},
        "npc_responses": {},
        "delivered": False,
        "final_responses": {},
    }
