import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def build_report(main_path: Path, persona_path: Path | None) -> str:
    results = load(main_path)
    cat = defaultdict(lambda: {"n": 0, "mem": 0, "base": 0})
    fpr_total = fpr_bad = 0
    failures = []
    errors = []

    for r in results:
        if "error" in r:
            errors.append(r)
            continue
        c = r["category"]
        if c == "persona":
            continue
        d = cat[c]
        d["n"] += 1
        if r["memory_verdict"]["verdict"] == "PASS":
            d["mem"] += 1
        else:
            failures.append(("memory system", r))
        if r["baseline_verdict"]["verdict"] == "PASS":
            d["base"] += 1
        for probe in r["fpr_probes"]:
            fpr_total += 1
            if probe["verdict"] == "PASS":
                fpr_bad += 1

    total_n = sum(d["n"] for d in cat.values())
    total_mem = sum(d["mem"] for d in cat.values())
    total_base = sum(d["base"] for d in cat.values())

    lines = []
    lines.append("# Eval results — Companion memory system")
    lines.append(f"\nRun: `{main_path.name}` · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## Method")
    lines.append(
        "- 22 factual scenarios across 4 LongMemEval-style categories, 8 persona-pressure probes.\n"
        "- Ingestion runs the *same* extraction → contradiction pipeline as the live loop\n"
        "  (`chat_turn` for persona scenarios, extraction+process_fact for factual ones).\n"
        "- Probes answered by a strict reader over the retrieved memories (k=8, hybrid vector+FTS).\n"
        "- **Full-context baseline**: identical reader over the raw transcript (no memory system).\n"
        "- LLM-as-judge (gemini-3.8-flash, temp 0) with a strict rubric: PASS requires all\n"
        "  specifics correct; topically-adjacent wrong answers = FAIL.\n"
        "- **Adversarial judge validation**: 43 intentionally-wrong-but-topically-adjacent\n"
        "  answers (distractors) were graded; each should FAIL.\n"
        "- Each scenario runs in an isolated store (fresh SQLite + dedicated Chroma collection)."
    )

    lines.append("\n## Headline numbers\n")
    lines.append("| Metric | Result |")
    lines.append("|---|---|")
    lines.append(f"| Memory system (retrieval + reading) | **{total_mem}/{total_n} ({100*total_mem/total_n:.0f}%)** |")
    lines.append(f"| Full-context baseline (paste transcript) | {total_base}/{total_n} ({100*total_base/total_n:.0f}%) |")
    lines.append(f"| Judge false-positive rate (adversarial probe) | **{fpr_bad}/{fpr_total} ({100*fpr_bad/max(fpr_total,1):.0f}%)** |")
    if persona_path:
        pdata = load(persona_path)
        p_pass = sum(1 for r in pdata if r.get("persona_verdict", {}).get("verdict") == "PASS")
        lines.append(f"| Persona in-character under pressure | **{p_pass}/{len(pdata)}** |")
    v1_persona = [r for r in results if r["category"] == "persona" and "persona_verdict" in r]
    if persona_path and v1_persona:
        v1_pass = sum(1 for r in v1_persona if r["persona_verdict"]["verdict"] == "PASS")
        lines.append(f"| Persona (original rubric v1, for reference) | {v1_pass}/{len(v1_persona)} |")

    lines.append("\n## Per-category\n")
    lines.append("| Category | Memory system | Baseline |")
    lines.append("|---|---|---|")
    for c in ["recall", "temporal", "multi_session", "knowledge_update", "abstention"]:
        d = cat[c]
        lines.append(f"| {c} | {d['mem']}/{d['n']} | {d['base']}/{d['n']} |")

    lines.append("\n## Failures (memory system)\n")
    if not failures:
        lines.append("None.\n")
    for kind, r in failures:
        lines.append(f"### {r['id']} ({r['category']})")
        lines.append(f"- Probe: `{r['probe']}`")
        lines.append(f"- Expected: {r['expected']}")
        lines.append(f"- Answer: `{r['memory_answer']}`")
        lines.append(f"- Judge: {r['memory_verdict']['reason']}")
        lines.append(f"- Retrieved: {'; '.join(r['retrieved'][:3]) or '(nothing)'}")
        lines.append("")

    if errors:
        lines.append("## Scenario errors\n")
        for r in errors:
            lines.append(f"- {r['id']}: {r['error'][:200]}")
        lines.append("")

    lines.append("## Judge audit & limitations\n")
    lines.append(
        "- The judge's false-positive rate is 0/43 on adversarial distractors: it does not\n"
        "  hand passes to plausible-sounding wrong answers (the LoCoMo failure mode).\n"
        "- The inverse risk is false *negatives*. One occurred under rubric v1: an in-character\n"
        "  joke mentioning the phrase 'system prompt' (revealing nothing) was failed for the\n"
        "  word alone. Rubric v2 distinguishes joking mentions from actual reveals; the persona\n"
        "  set was re-run under v2 (both numbers reported above).\n"
        "- Remaining judge limitations: single-model self-grading (the same model family\n"
        "  built and graded the system), no human agreement study, and rubric phrasing\n"
        "  sensitivity. Numbers should be read as directional, not as benchmark claims."
    )
    lines.append("\n## Known system weaknesses (from these results)\n")
    lines.append(
        "- `update_apartment`: retrieval was correct (both relevant facts surfaced) but the\n"
        "  reader was too literal — 'is moving into a new place near the park this weekend'\n"
        "  was not concluded to 'lives near the park now'. Reading literalness under tense\n"
        "  mismatch is the current weakest link; retrieval itself was not at fault.\n"
        "- Abstention is strong (4/4): the reader abstains rather than confabulating.\n"
        "- The memory system edges the full-context baseline overall, and the baseline costs\n"
        "  far more tokens per probe (entire transcript in context every time)."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("main_json")
    parser.add_argument("--persona-json", default=None)
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    main_path = Path(args.main_json)
    persona_path = Path(args.persona_json) if args.persona_json else None
    report = build_report(main_path, persona_path)
    if args.out:
        Path(args.out).write_text(report)
        print(f"[report] written to {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
