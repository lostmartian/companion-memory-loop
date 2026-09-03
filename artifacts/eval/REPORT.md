# Eval results — Companion memory system

Run: `eval_20260903_154417.json` · 2026-09-03 16:16

## Method
- 22 factual scenarios across 4 LongMemEval-style categories, 8 persona-pressure probes.
- Ingestion runs the *same* extraction → contradiction pipeline as the live loop
  (`chat_turn` for persona scenarios, extraction+process_fact for factual ones).
- Probes answered by a strict reader over the retrieved memories (k=8, hybrid vector+FTS).
- **Full-context baseline**: identical reader over the raw transcript (no memory system).
- LLM-as-judge (gemini-3.8-flash, temp 0) with a strict rubric: PASS requires all
  specifics correct; topically-adjacent wrong answers = FAIL.
- **Adversarial judge validation**: 43 intentionally-wrong-but-topically-adjacent
  answers (distractors) were graded; each should FAIL.
- Each scenario runs in an isolated store (fresh SQLite + dedicated Chroma collection).

## Headline numbers

| Metric | Result |
|---|---|
| Memory system (retrieval + reading) | **21/22 (95%)** |
| Full-context baseline (paste transcript) | 20/22 (91%) |
| Judge false-positive rate (adversarial probe) | **0/43 (0%)** |
| Persona in-character under pressure | **8/8** |
| Persona (original rubric v1, for reference) | 7/8 |

## Per-category

| Category | Memory system | Baseline |
|---|---|---|
| recall | 6/6 | 6/6 |
| temporal | 4/4 | 3/4 |
| multi_session | 3/3 | 3/3 |
| knowledge_update | 4/5 | 4/5 |
| abstention | 4/4 | 4/4 |

## Failures (memory system)

### update_apartment (knowledge_update)
- Probe: `Where do I live now?`
- Expected: near the park (moved from the Riverside apartment)
- Answer: `NOT IN MEMORY.`
- Judge: The expected answer contains known details, but the given answer incorrectly states that the information is not in memory.
- Retrieved: User is moving into a new place near the park this weekend.; User's lease at the Riverside apartment ended because it was getting expensive.

## Judge audit & limitations

- The judge's false-positive rate is 0/43 on adversarial distractors: it does not
  hand passes to plausible-sounding wrong answers (the LoCoMo failure mode).
- The inverse risk is false *negatives*. One occurred under rubric v1: an in-character
  joke mentioning the phrase 'system prompt' (revealing nothing) was failed for the
  word alone. Rubric v2 distinguishes joking mentions from actual reveals; the persona
  set was re-run under v2 (both numbers reported above).
- Remaining judge limitations: single-model self-grading (the same model family
  built and graded the system), no human agreement study, and rubric phrasing
  sensitivity. Numbers should be read as directional, not as benchmark claims.

## Known system weaknesses (from these results)

- `update_apartment`: retrieval was correct (both relevant facts surfaced) but the
  reader was too literal — 'is moving into a new place near the park this weekend'
  was not concluded to 'lives near the park now'. Reading literalness under tense
  mismatch is the current weakest link; retrieval itself was not at fault.
- Abstention is strong (4/4): the reader abstains rather than confabulating.
- The memory system edges the full-context baseline overall, and the baseline costs
  far more tokens per probe (entire transcript in context every time).
