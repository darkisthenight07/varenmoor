"""LangGraph construction: reviewer -> narrator -> director -> per-NPC pipelines -> reviewer."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from ..agents import (conversation_director_node, input_reviewer_node, make_npc_dialogue_node,
                      make_npc_emotion_node, make_npc_memory_node, narrator_node,
                      output_reviewer_node)
from ..state import AgentState
from ..story import Story, default_story
from ..utils import slug


def _node(char: str, kind: str) -> str:
    return f"npc_{slug(char)}_{kind}"


def build_agent(story: Story | None = None):
    story = story or default_story()
    characters = story.characters
    g = StateGraph(AgentState)

    g.add_node("input_reviewer", input_reviewer_node)
    g.add_node("narrator", narrator_node)
    g.add_node("director", conversation_director_node)
    g.add_node("output_reviewer", output_reviewer_node)

    for char in characters:
        g.add_node(_node(char, "dialogue"), make_npc_dialogue_node(char))
        g.add_node(_node(char, "emotion"), make_npc_emotion_node(char))
        g.add_node(_node(char, "memory"), make_npc_memory_node(char))
        g.add_edge(_node(char, "dialogue"), _node(char, "emotion"))
        g.add_edge(_node(char, "emotion"), _node(char, "memory"))
        g.add_edge(_node(char, "memory"), "output_reviewer")

    g.set_entry_point("input_reviewer")
    g.add_edge("input_reviewer", "narrator")
    g.add_edge("narrator", "director")

    def route_to_active_npcs(state: AgentState) -> list[str]:
        active = story.stage(state["stage"]).characters
        return [_node(c, "dialogue") for c in active] or ["output_reviewer"]

    g.add_conditional_edges(
        "director",
        route_to_active_npcs,
        {_node(c, "dialogue"): _node(c, "dialogue") for c in characters}
        | {"output_reviewer": "output_reviewer"},
    )
    g.add_edge("output_reviewer", END)
    return g.compile()
