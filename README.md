# Varenmoor

A multi-agent gothic-horror text game built on [LangGraph](https://langchain-ai.github.io/langgraph/).
You wake inside Vardenmoor, a cursed castle. A narrator, a cast of NPCs (each with emotions and
memory) and two reviewers respond to what you say. Different LLMs handle different jobs, with automatic
fallbacks, so it runs entirely on free-tier APIs (no local GPU needed).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # add ".[neo4j]" for graph memory, ".[dev]" for tests
cp .env.example .env        # add at least ONE API key (Groq is the quickest to get)
varenmoor models --ping     # verify every configured model actually answers
varenmoor                   # play (or: python -m varenmoor)
```

In-game: type to talk, `next` to skip to the next stage, `exit` to quit.
Flags: `-v` logs fallbacks, `--stats` prints LLM call counts at the end.

## Choosing models: `models.yaml`

`src/varenmoor/models.yaml` is the single place that decides which model does what. Run
`varenmoor init-config` to copy it next to you and edit it (`./models.yaml` overrides the packaged one;
`VARENMOOR_MODELS_FILE` or `--models FILE` overrides both).

| Role | What it does | Blocks the player? | Default chain |
|---|---|---|---|
| `narrator` | scene narration, story advance, NPC briefings | yes | Gemini Flash → Mistral Medium → Groq 120B |
| `npc_dialogue` | the NPC's spoken line | yes | Groq gpt-oss-120b → Mistral Medium → Gemini Flash |
| `input_review` | blocks off-story / injected input | yes | Groq gpt-oss-20b → Gemini Flash-Lite → Mistral Small |
| `output_review` | fixes lines that fail a check | rarely | Groq gpt-oss-20b → Mistral Small → Gemini Flash-Lite |
| `memory` | emotion changes + what to remember | **no (background)** | Mistral Small → Gemini Flash-Lite → Groq gpt-oss-20b |

- **Fallbacks:** if a model errors, times out, or is rate-limited, the next in the chain answers. A failing
  model is benched (30s, doubling on repeats; a bad API key is benched for the session).
- **Only one key?** Models whose provider has no key are skipped, so a single `GROQ_API_KEY` is enough.
- **Pacing:** each model's `rpm` makes Varenmoor slow itself down instead of hitting a 429.
- **Adding a model or provider:** add an entry under `models:` (any OpenAI-compatible endpoint works via
  `kind: openai_compat`) and reference it in a role's `chain`.
- Free-tier quotas change often and sources disagree. Treat `rpm` values as safe guesses and check
  each provider's dashboard. `varenmoor models --ping` is the ground truth.

## Turn pipeline

```
input_reviewer ─► scene (narrate + advance? + brief NPCs) ─► npc dialogue ─► output_reviewer ─► player
                                                                                     └─► memory manager (background)
```

A normal turn makes **3 blocking LLM calls plus 1 background call** (it was 7, all sequential):

- Narrator and director merged into one `scene` call.
- Emotion engine and memory system merged into one `memory` call, run **after** the reply is shown.
- Output reviewer runs cheap deterministic checks first (stage directions, markup, AI talk, speaker labels,
  characters from future stages) and calls the LLM only when one trips.
- Input review skips the LLM for obvious injection attempts (regex) and truncates input to 500 chars.
- No memory call when the player's input was blanked as injection.

Tunable under `pipeline:` in `models.yaml` (`input_review: llm|heuristic|off`,
`output_review: on_flag|always|off`, `background_memory`, `skip_memory_on_silence`).

## Memory

- **Short-term:** last 10 interactions per (player, character), JSON in `memory_store/`.
- **Emotions:** happiness / anger / trust per (player, character), **persisted** across sessions.
- **Long-term:** relationship edges in Neo4j, scoped per player. Optional: unset `NEO4J_*` to run without it.

## Layout

```
src/varenmoor/
  models.yaml         which LLM does what (edit me)
  llm/                settings (validated YAML), providers, router (fallback/cooldown/pacing)
  game.py             session: stages, turns, background memory
  cli.py              terminal UI + `models` / `init-config` commands
  agents/             input_reviewer, narrator (scene), npc, output_reviewer, memory_manager
  graph/builder.py    LangGraph wiring
  memory/             short_term, long_term (Neo4j), emotion, store (atomic JSON)
  story/              loader + data/vardenmoor.yaml (all story content)
tests/                59 tests, no API keys needed
```

## Editing the story

Edit `src/varenmoor/story/data/vardenmoor.yaml`. Stages play in list order; each has a description,
the characters present, and per-character rules. An optional `objective` steers the scene.

## Tests

```bash
pip install -e ".[dev]" && pytest
```
