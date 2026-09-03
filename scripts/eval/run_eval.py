import argparse
import json
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from companion import config, extract, llm, retrieve
from companion.contradictions import process_fact
from companion.loop import NullConsole, chat_turn, load_persona
from companion.store import Store
from scripts.eval.judge import judge_answer, judge_persona
from scripts.eval.scenarios import ALL_SCENARIOS, FACT_SCENARIOS, PERSONA_SCENARIOS

READER_SYSTEM = """You answer questions about a person using ONLY the provided context.
You may draw direct logical conclusions from the context (e.g. "broke up with Sam last
week" implies "not dating anyone right now"; " switched to day shifts" implies current
shifts are day shifts).
Answer in one or two sentences.
If the context does not contain the answer and no direct conclusion can be drawn, reply
exactly: NOT IN MEMORY.
Never invent names, dates, or details that are not in the context."""


def reader_answer(probe: str, context: str) -> str:
    return llm.generate(
        f"CONTEXT:\n{context}\n\nQUESTION: {probe}",
        model=config.UTILITY_MODEL,
        system=READER_SYSTEM,
        temperature=0.0,
    ).strip()


def ingest(store: Store, turns: list[str]) -> None:
    for i, msg in enumerate(turns, 1):
        recent = "\n".join(turns[max(0, i - 3) : i - 1])
        for fact in extract.extract_facts(msg, recent_context=recent):
            process_fact(store, fact, source_turn=i)


def run_fact_scenario(sc, eval_dir: Path) -> dict:
    store = Store(eval_dir / f"{sc.id}.sqlite3")
    ingest(store, sc.turns)
    memories = retrieve.retrieve(store, sc.probe, k=8)
    mem_ctx = "\n".join(f"- {row['text']}" for row, _ in memories) or "(no memories retrieved)"
    transcript = "\n".join(f"user: {t}" for t in sc.turns)

    mem_answer = reader_answer(sc.probe, f"MEMORIES:\n{mem_ctx}")
    full_answer = reader_answer(sc.probe, f"FULL TRANSCRIPT:\n{transcript}")

    mem_verdict = judge_answer(sc.category, sc.expected, mem_answer)
    full_verdict = judge_answer(sc.category, sc.expected, full_answer)

    fpr_rows = []
    for distractor in sc.distractors:
        v = judge_answer(sc.category, sc.expected, distractor)
        fpr_rows.append({"distractor": distractor, **v})
        if v["verdict"] == "PASS":
            print(f"  [FPR] judge PASSED a wrong answer for {sc.id}: {distractor}", file=sys.stderr)

    store.close()
    return {
        "id": sc.id,
        "category": sc.category,
        "probe": sc.probe,
        "expected": sc.expected,
        "retrieved": [row["text"] for row, _ in memories],
        "memory_answer": mem_answer,
        "memory_verdict": mem_verdict,
        "baseline_answer": full_answer,
        "baseline_verdict": full_verdict,
        "fpr_probes": fpr_rows,
    }


def run_persona_scenario(sc, eval_dir: Path) -> dict:
    store = Store(eval_dir / f"{sc.id}.sqlite3")
    persona = load_persona()
    out = NullConsole()
    for turn in sc.turns:
        chat_turn(store, f"eval_{sc.id}", turn, persona, out)
    reply = chat_turn(store, f"eval_{sc.id}", sc.probe, persona, out)
    verdict = judge_persona(sc.probe, reply)
    store.close()
    return {
        "id": sc.id,
        "category": sc.category,
        "probe": sc.probe,
        "expected": sc.expected,
        "persona_reply": reply,
        "persona_verdict": verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None, help="comma-separated scenario ids")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_dir = Path(tempfile.mkdtemp(prefix=f"companion_eval_{run_id}_"))
    config.FACT_COLLECTION = f"eval_{run_id}"
    print(f"[eval] run {run_id}, collection={config.FACT_COLLECTION}", file=sys.stderr)

    selected = ALL_SCENARIOS
    if args.only:
        wanted = set(args.only.split(","))
        selected = [s for s in ALL_SCENARIOS if s.id in wanted]

    results = []
    for i, sc in enumerate(selected, 1):
        print(f"[eval] {i}/{len(selected)} {sc.id} ({sc.category})", file=sys.stderr)
        try:
            if sc in PERSONA_SCENARIOS:
                results.append(run_persona_scenario(sc, eval_dir))
            else:
                results.append(run_fact_scenario(sc, eval_dir))
        except Exception as e:
            print(f"  [error] {sc.id}: {e}", file=sys.stderr)
            results.append({"id": sc.id, "category": sc.category, "error": str(e)})

    out_dir = Path(__file__).resolve().parents[2] / "internal_documentation" / "eval_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_{run_id}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"[eval] results written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
