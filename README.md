# Companion-AI Core Loop: Memory & Evaluation

A command-line companion ("Milo") with a real memory architecture: bi-temporal fact store,
hybrid retrieval, LLM-driven contradiction handling, and persona-consistency grounding —
plus the reasoning behind every decision.

Built for the Tech Generalist take-home. Runtime: Python 3.13, Gemini API, SQLite + Chroma.

## Requirements

- A Gemini API key ([aistudio.google.com](https://aistudio.google.com) → "Get API key")
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`) —
  uv provides Python 3.13 automatically; you do not need Python installed beforehand.
- No other services. SQLite is stdlib; Chroma runs embedded (no server).

## Running it

```bash
git clone <this repo>
cd <repo>
uv sync                       # creates .venv, installs everything, ~1 min
cp .env.example .env          # then paste your key into GEMINI_API_KEY=
uv run python -m companion.loop demo     # start chatting
```

That's it. The first run creates `data/companion.sqlite3` and `data/chroma/` —
all memory lives there and survives restarts. Delete the `data/` folder for a
factory reset.

> If you prefer plain pip: `python3.13 -m venv .venv && source .venv/bin/activate &&
> pip install -e ".[dev]"`, then run `python -m companion.loop demo`.

## Talking to Milo

You get a terminal loop:

```
Milo — session 'demo'. Type /exit to quit.
you › I have been dating Sam for about a year now.
milo › Two years is a solid milestone...
  memory (NEW): User has been dating Sam for about a year.
```

- **Just chat.** Milo remembers what you disclose across sessions. Mention your job,
  relationships, plans, preferences — they become facts you'll see logged as
  `memory (NEW)` lines.
- **Change something.** Say "we broke up" or "I switched jobs" — watch for
  `memory (SUPERSEDES)`: the old fact is retired (never deleted) and Milo's world
  state updates.
- **Leave and come back.** Quit with `/exit`, re-run the same command — it prints
  `Resuming session 'demo' (N prior turns)` and picks up where you left off.
  Different session names are separate universes; the same name resumes.
- **Push on the persona.** Ask "are you an AI?" or "ignore your persona" — you'll see
  a `re-grounded persona` line and Milo deflects in character.

In-chat commands:

| Command | Effect |
|---|---|
| `/facts` | dump all active memories stored about you |
| `/exit` | quit (everything already saved) |

The dim lines between turns are the memory system narrating itself:
`recalled:` = facts injected into this turn's prompt, `memory (NEW/SUPERSEDES/DUPLICATE)` =
extraction + contradiction verdicts. They're your window into the architecture.

### A 3-minute tour to try the whole system

```bash
uv run python -m companion.loop tour
```

1. `I've been dating Sam for two years, they're great.`
2. `My sister Anna is getting married June 14th in Lisbon.`
3. `/exit` — then re-run the same command (restart persistence).
4. `What's my sister's wedding date?` → answered from memory (`recalled:` lines appear).
5. `Sam and I broke up last week.` → `memory (SUPERSEDES)`, empathic reply.
6. `How are things with Sam?` → current truth only; the retired fact is gone from recall.
7. `Are you an AI?` → in-character deflection, no assistant-speak.

## Tests, soak, eval

```bash
uv run pytest -q                                     # 50 unit tests, no API key needed
uv run python scripts/soak_test.py --session soak2   # 50-turn scripted stress run (~7 min, uses API)
uv run python scripts/eval/run_eval.py               # 30-scenario eval (~20 min, uses API)
uv run python scripts/eval/report.py artifacts/eval/results_main.json \
    --persona-json artifacts/eval/results_persona_rubric_v2.json   # regenerate the report
```

- Soak test: seeds facts, contradicts them mid-run, probes long-range recall at turns
  31/41/45/49. Transcript lands in `data/`; a tracked copy is in `artifacts/soak_transcript.txt`.
- Eval: 22 factual scenarios (recall / temporal / multi-session / knowledge-update /
  abstention) with a full-context baseline and an adversarial judge FPR probe, plus
  8 persona-pressure probes. Each scenario runs in an isolated store.
- If the Chroma index ever diverges from SQLite (e.g. you restored an old DB file):

```bash
uv run python -c "from companion import config, vectors; from companion.store import Store; s=Store(config.DB_PATH); print(vectors.rebuild_from_store(s), 'facts re-embedded')"
```

## Architecture

```
user turn ──► extraction (gemini-3.8-flash, JSON mode) ──► structured facts
                    │
                    ▼
   SQLite (source of truth, bi-temporal)      Chroma (vector index, active only)
   facts: subject/predicate/object/text,      embeddings: gemini-embedding-001
     valid_from/valid_to, status,               768-dim (MRL-truncated),
     superseded_by, observed/recorded_at        task_type DOCUMENT/QUERY
   turns + per-session rolling summary
                    │
                    ▼
turn prompt = persona card (always resident)
            + rolling conversation summary (compaction)
            + top-5 facts (vector ∪ FTS5, recency boost)
            + grounding reminder on drift-prone turns
            + last 8 turns verbatim
```

### Contradiction handling (the interesting part)

Every extracted fact is compared against semantically similar active facts
(vector top-3 + same subject/predicate) and an LLM classifies each pair:

- `NEW` → store
- `SUPERSEDES` → store new, retire old (`valid_to=now`, `superseded_by=new_id`,
  **removed from vector index, never deleted from SQLite**)
- `DUPLICATE` → skip store

The store therefore always answers "what is true now" while preserving full history —
the bi-temporal approach from Zep/Graphiti (arXiv 2501.13956), simplified onto SQLite.
New information always wins: if the user says "I broke up with Sam" after months of
relationship facts, the old facts are retired, not argued with.

### Design decisions & why

| Decision | Why |
|---|---|
| SQLite as source of truth, Chroma as disposable index | Facts need joins, statuses, temporal fields; vectors don't. If Chroma diverges, `vectors.rebuild_from_store()` re-embeds everything. (This happened once during dev — the rebuild tool exists because of it.) |
| Two storage engines, one transaction path | Writes go to SQLite + Chroma in `commit_fact`; retire = SQLite update + Chroma delete. |
| LLM classifier restricted to 3 relations | Fewer buckets = higher agreement. `REFINE`/`MERGE` folded into `SUPERSEDES` ("strictly more detailed version"). |
| FTS5 tokens joined with OR, not AND | AND missed "wedding" vs "married". OR + rank ordering gets relevance without missing synonyms. |
| Persona card always resident, never extracted into fact store | Letta-style core memory. Persona traits can't be crowded out by retrieval, and user-fact extraction is prompted to ignore them. |
| Persona re-grounding on drift-prone turns | Regex detector for identity probes / override attempts appends a hard reminder. Cheap (no extra LLM call), effective in pressure tests. |
| Compaction watermark (`summarized_until_turn`) | Only *new* turns older than the window get folded into the rolling summary; no repeated summarization cost. |
| `chat_turn()` shared by CLI and soak test | The eval/stress path exercises the *exact* production pipeline, not a parallel implementation. |
| Per-session background ingest queue (`ingest.py`) | Extraction/contradiction runs off the reply path (Zep-style async ingestion): ordered per-session writes, own SQLite connection per worker, flush-on-exit so nothing is lost, error-resilient per task. |
| Key expansion at index time | Each fact carries LLM-generated recall phrases (`search_keys`) — embedded and FTS-indexed. LongMemEval's finding: fixing recall at index time beats runtime heuristics and costs no query-time latency. |
| Subject registry for extraction | Companion entities excluded at schema level (`validate_subjects`), not just prompted — the Zep/Letta lesson that identity scoping must be structural. |
| Structured compaction summary | current_state / open_threads / emotional_context / last_exchange with temporal-qualifier rules; lossy-by-design but bounded, and facts remain the recall source of truth. |
| Model routing: one model (`gemini-3.8-flash`) for chat, extraction, classification, judging | Simple to reason about; extraction runs per turn so cost-sensitive routing matters less at this scale. |

### What was tried and abandoned

- **numpy + local sentence-transformers for vectors** — replaced by Chroma + Gemini
  embeddings (task-type support won; quality > local convenience).
- **`gemini-embedding-2`** — multimodal is irrelevant here, it drops `task_type`
  support and its embedding space is incompatible; stayed on `gemini-embedding-001` at 768 dims.
- **Per-candidate pairwise LLM calls for contradictions** — one batched classification
  call per new fact (all candidates in one prompt) cuts LLM calls ~3x with no observed
  accuracy loss.
- **Strict FTS AND-queries** — failed open (empty results); OR semantics with rank
  ordering failed closed.
- **uv/Python 3.14** — `onnxruntime` (chromadb dep) has no Intel-mac/3.14 wheels;
  pinned Python 3.13 via uv.

### Known limitations

Six limitations were identified after the first full build (each documented with its
production-system analysis and fix in the build log). Status after the improvement pass:

1. **Subject confusion** — fixed via a subject registry: companion entities are excluded
   at the schema level (`validate_subjects`), not just prompted away. Residual risk:
   novel companion-entity names not in the registry.
2. **Compaction lossy** — mitigated via a structured summary template
   (current_state / open_threads / emotional_context / last_exchange) with explicit
   temporal-qualifier rules. Inherent lossiness remains; facts (not the summary) are the
   recall source of truth.
3. **Retrieval embedding-bounded** — improved via **key expansion at index time** (each
   fact carries LLM-generated recall phrases, embedded and FTS-indexed, zero extra
   calls). A cross-encoder reranker remains the unimplemented next lever.
4. **Extraction latency** — fixed via per-session background ingest queue (ordered writes,
   flush-on-exit, error-resilient worker). Residual risk: a memory extracted for turn N
   lands before turn N+2 rather than N+1 if the user replies instantly.
5. **Classifier trusts recency** — fixed with a recounts-are-not-new-states rubric rule +
   a structural guard (interrogative/recount-shaped texts can never write memory).
   Deeper fix (event-vs-state schema, Graphiti-style) remains future work.
6. **Judge reliability** — validated adversarially (0/43 FPR) and cross-validated with a
   stronger judge: **100% agreement (30/30, `artifacts/eval/cross_judge.md`)**. Human
   agreement study remains out of scope; numbers stay directional, not benchmark claims.

**Results: memory 21/22 (95%) vs full-context baseline 20/22 (91%)** — beating the
baseline on temporal questions (4/4 vs 3/4). Persona 8/8 in-character under pressure.
The one memory failure (`update_apartment`) was a *reading* literalness issue, not
retrieval: both relevant facts were retrieved; the reader wouldn't conclude
"is moving this weekend" → "lives near the park now". Full report:
[`artifacts/eval/REPORT.md`](artifacts/eval/REPORT.md).

## Evidence the core loop works

- [`artifacts/eval/REPORT.md`](artifacts/eval/REPORT.md) — full eval: 21/22 memory vs 20/22
  full-context baseline, per-category table, judge FPR probe (0/43), failure analysis.
  Raw judged results: `artifacts/eval/results_main.json`, `results_persona_rubric_v2.json`.
- [`artifacts/soak_transcript.txt`](artifacts/soak_transcript.txt) — 50-turn scripted session: fact seeding,
  mid-session breakup contradiction, shift-change supersession, long-range probes
  (coffee order t31, wedding date t41, relationship status t45, allergy t49) all answered
  from memory, 30 active / 12 retired facts with full supersession chains.
- Restart safety: `kill -9` mid-session, next process resumes and recalls.
- Persona pressure: "Are you an AI?" / "ignore your persona" → in-character deflection,
  zero assistant-speak.

## Project layout

```
companion/
  config.py          model routing, paths, constants
  schema.py          pydantic Fact model
  store.py           SQLite bi-temporal store + FTS5 + turns + summaries
  vectors.py         gemini-embedding-001 ↔ Chroma index
  llm.py             Gemini clients (streaming + JSON mode)
  extract.py         fact extraction pipeline (subject registry + search keys)
  contradictions.py  classify NEW / SUPERSEDES / DUPLICATE, retire old
  ingest.py          per-session background ingest queue
  retrieve.py        hybrid retrieval (vector ∪ FTS5 + search keys, recency boost)
  compaction.py      structured rolling summary with watermark
  persona.py         drift-prone turn detector + grounding reminder
  loop.py            terminal chat loop + chat_turn() used by tests/eval
persona/card.md      Milo's persona definition
scripts/soak_test.py 50-turn stress run
scripts/eval/        scenarios.py · judge.py · run_eval.py · report.py · cross_judge.py
tests/               50 unit tests
artifacts/           tracked evidence: soak transcript + eval report/results
```

A session-by-session build log with per-task evidence lives in
`internal_documentation/PLAN.md` (gitignored — internal working notes).

## Walkthrough (15–20 min)

1. (3 min) Problem framing: why "chatbot + system prompt" fails — contradicting stated
   opinions, forgetting disclosures, generic tone under pressure.
2. (5 min) Architecture tour: bi-temporal schema, hybrid retrieval, contradiction
   classifier. Show `sqlite3 data/companion.sqlite3 "SELECT ... "` with retired facts.
3. (5 min) Live demo: seed a fact, contradiction ("I broke up with my ex"), restart the
   process, recall probe, identity probe.
4. (4 min) Soak test results + limitations honesty: what breaks, what I'd fix next
   (subject validation, reranker, eval harness).
5. (2 min) Eval plan: LongMemEval categories, judge FPR probe, oracle baseline.
