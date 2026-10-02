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

In-game: just say or do things. Scenes open on their own (the narrator sets the scene and the
character speaks first) and the story moves on by itself when something in the scene happens, so
there is nothing to skip. Type `exit` to quit.
Flags: `-v` logs fallbacks, `--stats` prints LLM call counts at the end, `--dev` enables `/skip`
(jump to the next scene, for testing).

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

## How the story progresses

Every stage has an ordered plan of **beats**. A beat is either something a character says (`by: npc`)
or something the player does (`by: player`). The scene ends when its last beat is done, and the next
scene opens straight away, so the story flows from conversation and action rather than commands.

- **NPC beats** are delivered one per turn, in order, in the character's own voice. The Old Woman
  welcomes you on turn one and asks her favour on turn two. She doesn't dump everything at once.
- **Player beats** (leave the room, agree to the favour, touch the painting, tie up the Doctor,
  fight the King) are judged by the narrator from what you say or do. "I head out" counts; you never
  need magic words. Some beats have a `min_turns` so a conversation can't be skipped by accident.
- **Cutscenes** are stages with no beats (the Doctor's cellar, the epilogue). They are narrated once
  and the story continues on its own.
- **Nobody gets stuck.** Past half of a stage's `max_turns` the world starts steering you toward the
  current beat (the beat's `hint`: an open door, chains within reach). Past `max_turns` events carry
  you along.
- Narration only appears when something happens (a scene opens, you act or move, a beat lands). While
  you are just talking, the characters' words carry the scene. Characters and narrator both see the
  recent conversation, so replies respond to what you actually said.
- Emotions (happiness / anger / trust) still shape how each character sounds, but are never shown.

## Turn pipeline

```
input_reviewer ─► scene (narrate + advance? + brief NPCs) ─► npc dialogue ─► output_reviewer ─► player
                                                                                     └─► memory manager (background)
```

A scene opening makes 2 calls (scene + the character's first line; no input review, no memory).
A normal turn makes **3 blocking LLM calls plus 1 background call** (it was 7, all sequential):

- Narrator, beat judge and director merged into one `scene` call.
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
  game.py             session: beat progression, scene opening, background memory
  web.py              FastAPI wrapper used by the web UI (see Deploying)
  cli.py              terminal UI + `models` / `init-config` commands
  agents/             input_reviewer, narrator (scene), npc, output_reviewer, memory_manager
  graph/builder.py    LangGraph wiring
  memory/             short_term, long_term (Neo4j), emotion, store (atomic JSON)
  story/              loader + data/vardenmoor.yaml (all story content)
web/                static chat UI (deployed on Vercel)
render.yaml         Render blueprint for the API
tests/              83 tests, no API keys needed
```

## Editing the story

Edit `src/varenmoor/story/data/vardenmoor.yaml`. Stages play in list order. Per stage:

```yaml
- id: checkpoint1
  description: what the player sees (the narrator paraphrases it; it is never printed verbatim)
  lore: director-only background the narrator may colour the scene with, never states outright
  characters: [mouse]
  max_turns: 14            # safety net, see "How the story progresses"
  beats:
  - id: greet
    by: npc                # a character conveys it (one per turn, in order)
    text: The Mouse greets the player like an old friend.
  - id: leave
    by: player             # the player has to do it; the narrator judges it
    min_turns: 2           # optional: can't complete before this many turns in the scene
    text: The player moves on, leaving the Mouse behind.
    hint: lamplight spills from a doorway at the far end   # optional: surfaced if the scene drags
  rules:
    mouse: |
      the character's voice, secrets and limits
```

`who: <character>` on an npc beat picks the speaker when several characters share a stage. A stage
with no `characters` and no `beats` is a cutscene (describe it, put the narration style under
`rules.environment`). Stages written the old way (no `beats`) still work: they get one player beat
made from `objective`.

## Tests

```bash
pip install -e ".[dev]" && pytest
```