"""Final gate. Cheap deterministic checks run on every line; the LLM rewrites a line only when a
check trips (pipeline.output_review = on_flag), which also stops needless rewrites from flattening
character voice."""
from __future__ import annotations

import re

from .. import llm
from ..state import AgentState
from ..story import Story, default_story

MAX_LINE_CHARS = 1200

# (label, pattern) — anything here means the line needs a rewrite.
ARTIFACTS: list[tuple[str, re.Pattern]] = [
    ("stage direction", re.compile(r"\*[^*\n]{2,}\*")),
    ("markup/tool syntax", re.compile(r"</?[a-zA-Z][^>]*>|\{\s*\"|\bfunction_call\b|\btool_call\b|```")),
    ("meta/AI reference", re.compile(r"\bas an ai\b|\blanguage model\b|\bsystem prompt\b|\bthe player character\b", re.I)),
    ("numeric emotion", re.compile(r"\b(happiness|anger|trust)\b\s*[:=]?\s*\d", re.I)),
]

PROMPT = """
You are the Output Reviewer for Vardenmoor — the final gate before dialogue reaches the player.
You enforce story integrity and technical cleanliness.

STORY ARC (to detect spoilers and out-of-place references):
{story_arc}

STAGE: {stage}
CHARACTER RULES for {char} at this stage:
{char_rules}

A pre-check flagged this response: {flags}

REVIEW THE FOLLOWING RESPONSE from {char}:
"{response}"

CHECK AND FIX each violation type below. Rewrite the minimum necessary to fix it.
If none are found, return the response unchanged.

VIOLATION CHECKLIST:
1. TECHNICAL ARTIFACTS — strip tool call syntax, JSON fragments, XML tags, stage directions, speaker labels
2. META-COMMENTARY — remove any mention of memory, tools, game state, emotions as numbers, or AI
3. CHARACTER BREAK — if the response contradicts the character rules above (wrong tone, reveals
a secret not yet permitted, or acts unlike their established self), rewrite to match the rules
4. FUTURE SPOILERS — if the response references AHEAD stages from the arc, remove that content
5. TONE FAILURE — if the response is too cheerful, too casual, too modern, or otherwise
breaks gothic horror atmosphere, adjust the wording to fit

Return ONLY the final dialogue line. No explanation, no quotes, no labels.
"""


def _spoiler_names(story: Story, stage_id: str) -> list[str]:
    """Characters who only appear in AHEAD stages (so this NPC shouldn't know them yet)."""
    ids = [s.id for s in story.stages]
    idx = ids.index(stage_id)
    seen = {c for s in story.stages[: idx + 1] for c in s.characters}
    return [c for s in story.stages[idx + 1:] for c in s.characters if c not in seen]


def check_line(story: Story, stage_id: str, response: str) -> list[str]:
    """Deterministic problems found in a line; empty list means it's clean."""
    flags = [label for label, pat in ARTIFACTS if pat.search(response)]
    names = "|".join(re.escape(c.replace("_", " ")) for c in story.characters) + "|npc|narrator"
    if re.search(rf"^\s*\[?({names})\]?\s*:", response.replace("_", " "), re.I | re.M):
        flags.append("speaker label")
    if not response.strip() or response.strip() == "[silence]":
        return []
    if len(response) > MAX_LINE_CHARS:
        flags.append("too long")
    for name in set(_spoiler_names(story, stage_id)):
        if re.search(rf"\b{re.escape(name.replace('_', ' '))}\b", response, re.I):
            flags.append(f"possible spoiler: '{name.replace('_', ' ')}'")
    return flags


def output_reviewer_node(state: AgentState) -> dict:
    story = default_story()
    stage = story.stage(state["stage"])
    mode = llm.pipeline().output_review
    arc = story.arc_summary(stage.id)
    cleaned: dict[str, str] = {}
    for char, response in state.get("npc_responses", {}).items():
        flags = check_line(story, stage.id, response)
        if mode == "off" or (mode == "on_flag" and not flags):
            cleaned[char] = response
            continue
        try:
            fixed = llm.ask("output_review", PROMPT.format(
                story_arc=arc, stage=stage.id, char=char, char_rules=stage.rule_for(char),
                flags=", ".join(flags) or "none (routine review)", response=response))
        except llm.AllModelsFailed:
            fixed = ""
        cleaned[char] = fixed or response
    return {"final_responses": cleaned}
