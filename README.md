# Varenmoor

A multi-agent gothic-horror text game built on [LangGraph](https://langchain-ai.github.io/langgraph/).
You wake inside Vardenmoor, a cursed castle. A narrator, a conversation director, and a cast of NPCs
(each with emotions and memory) respond to what you say, and a reviewer gates every line.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # add ".[neo4j]" for long-term graph memory, ".[dev]" for tests
cp .env.example .env        # then set GROQ_API_KEY
varenmoor                   # or: python -m varenmoor
```

In-game: type to talk, `next` to skip to the next stage, `exit` to quit.

## Layout

```
src/varenmoor/
  cli.py              terminal game loop
  config.py, llm.py   settings and the single place models are created
  state.py            LangGraph state
  graph/builder.py    wires the agents into a graph
  agents/             input_reviewer, narrator, director, npc (dialogue/emotion/memory), output_reviewer
  memory/             short_term (JSON), long_term (Neo4j, optional), emotion
  story/              loader + data/vardenmoor.yaml (all story content lives here)
tests/                pytest suite; uses a fake LLM, no API key needed
```

## Turn pipeline

`input_reviewer → narrator → director → [npc dialogue → emotion → memory] → output_reviewer`

## Memory

- **Short-term:** last 10 interactions per (player, character), persisted to `memory_store/`.
- **Long-term:** relationship edges in Neo4j, scoped per player. Optional: if `NEO4J_*` is unset the game runs without it.
- **Emotions:** happiness / anger / trust per (player, character), in-process.

## Editing the story

Edit `src/varenmoor/story/data/vardenmoor.yaml`. Stages play in list order; each has a description,
the characters present, and per-character rules. An optional `objective` steers the scene.

## Tests

```bash
pip install -e ".[dev]" && pytest
```
