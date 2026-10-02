"""LangGraph: input_reviewer -> scene -> [npc dialogue] -> output_reviewer.
Memory/emotion updates happen after the reply (see game.Game), not inside the graph."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from ..agents import input_reviewer_node, make_npc_dialogue_node, output_reviewer_node, scene_node
from ..state import AgentState
from ..story import Story, default_story
from ..utils import slug


def _node(char: str) -> str:
    return f"npc_{slug(char)}_dialogue"


def build_agent(story: Story | None = None):
    story = story or default_story()
    g = StateGraph(AgentState)
    g.add_node("input_reviewer", input_reviewer_node)
    g.add_node("scene", scene_node)
    g.add_node("output_reviewer", output_reviewer_node)
    for char in story.characters:
        g.add_node(_node(char), make_npc_dialogue_node(char))
        g.add_edge(_node(char), "output_reviewer")

    g.set_entry_point("input_reviewer")
    g.add_edge("input_reviewer", "scene")

    def route(state: AgentState) -> list[str]:
        stage = story.stage(state["stage"])
        # A scene whose last beat the player just completed ends without another NPC line.
        if stage.beats and state.get("beat_idx", 0) >= len(stage.beats):
            return ["output_reviewer"]
        if state.get("skip_npc"):          # the narrator delivered a beat on its own
            return ["output_reviewer"]
        return [_node(c) for c in stage.characters] or ["output_reviewer"]

    g.add_conditional_edges("scene", route,
                            {_node(c): _node(c) for c in story.characters} | {"output_reviewer": "output_reviewer"})
    g.add_edge("output_reviewer", END)
    return g.compile()
