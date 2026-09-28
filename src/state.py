"""LangGraph agent state."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    player_id: str
    stage: str
    player_input: str
    sanitized_input: str                        # after input review
    narration: str
    advance_stage: bool                         # narrator says the scene is complete
    dialogue_prompts: dict[str, str]            # char -> director's directive
    npc_responses: Annotated[dict, operator.or_]  # char -> raw line (merged across parallel NPCs)
    final_responses: dict[str, str]             # char -> reviewed line


def initial_state(player_id: str, stage: str, player_input: str) -> AgentState:
    return {
        "player_id": player_id,
        "stage": stage,
        "player_input": player_input,
        "sanitized_input": "",
        "narration": "",
        "advance_stage": False,
        "dialogue_prompts": {},
        "npc_responses": {},
        "final_responses": {},
    }
