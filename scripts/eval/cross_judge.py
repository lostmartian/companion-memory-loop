"""Re-judge an existing eval run with a different (stronger) judge model and report
agreement. Judge-only: no scenarios are re-run, so this measures judge variance, not
system variance."""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.eval.judge import judge_answer, judge_persona


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("main_json")
    parser.add_argument("--persona-json", default=None)
    parser.add_argument("--model", default="gemini-3.1-pro-preview")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    results = json.loads(Path(args.main_json).read_text())
    persona_results = []
    if args.persona_json:
        persona_results = json.loads(Path(args.persona_json).read_text())

    agree = disagree = errors = 0
    by_cat = defaultdict(lambda: [0, 0])
    disagreements = []

    for r in results:
        if "error" in r or "memory_verdict" not in r:
            continue
        v2 = judge_answer(r["category"], r["expected"], r["memory_answer"], model=args.model)
        v1 = r["memory_verdict"]["verdict"]
        by_cat[r["category"]][0] += 1
        if v2["verdict"] == "ERROR":
            errors += 1
            continue
        if v2["verdict"] == v1:
            agree += 1
            by_cat[r["category"]][1] += 1
        else:
            disagree += 1
            disagreements.append(
                {
                    "id": r["id"],
                    "rubric_v1": v1,
                    f"{args.model}": v2["verdict"],
                    "answer": r["memory_answer"][:120],
                    "expected": r["expected"],
                    "reason": v2.get("reason", "")[:160],
                }
            )

    p_agree = p_disagree = 0
    p_disagreements = []
    for r in persona_results:
        if "persona_verdict" not in r:
            continue
        v2 = judge_persona(r["probe"], r["persona_reply"], model=args.model)
        v1 = r["persona_verdict"]["verdict"]
        if v2["verdict"] == "ERROR":
            errors += 1
            continue
        if v2["verdict"] == v1:
            p_agree += 1
        else:
            p_disagree += 1
            p_disagreements.append(
                {
                    "id": r["id"],
                    "rubric_v1": v1,
                    f"{args.model}": v2["verdict"],
                    "reply": r["persona_reply"][:160],
                    "reason": v2.get("reason", "")[:160],
                }
            )

    total = agree + disagree
    lines = [
        "# Cross-judge agreement",
        f"\nPrimary judge: `{args.model}` re-grading answers produced under the original rubric run.\n",
        f"- Factual scenarios: agreement **{agree}/{total} ({100*agree/max(total,1):.0f}%)**",
        f"- Persona probes: agreement **{p_agree}/{p_agree + p_disagree}**",
        f"- Judge errors: {errors}",
        "",
        "## Per-category agreement",
        "",
        "| Category | Agree / n |",
        "|---|---|",
    ]
    for cat, (n, a) in sorted(by_cat.items()):
        lines.append(f"| {cat} | {a}/{n} |")
    if disagreements:
        lines.append("\n## Disagreements (factual)\n")
        for d in disagreements:
            lines.append(f"### {d['id']}")
            lines.append(f"- original: **{d['rubric_v1']}** · {args.model}: **{d[args.model]}**")
            lines.append(f"- answer: `{d['answer']}`")
            lines.append(f"- {args.model} reason: {d['reason']}")
    if p_disagreements:
        lines.append("\n## Disagreements (persona)\n")
        for d in p_disagreements:
            lines.append(f"### {d['id']}")
            lines.append(f"- original: **{d['rubric_v1']}** · {args.model}: **{d[args.model]}**")
            lines.append(f"- reason: {d['reason']}")

    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(report)
        print(f"[cross-judge] report written to {args.out}", file=sys.stderr)
        out_json = Path(args.out).with_suffix(".json")
        out_json.write_text(
            json.dumps(
                {
                    "model": args.model,
                    "factual_agreement": f"{agree}/{total}",
                    "persona_agreement": f"{p_agree}/{p_agree + p_disagree}",
                    "disagreements": disagreements + p_disagreements,
                    "generated": datetime.now().isoformat(),
                },
                indent=2,
            )
        )
    else:
        print(report)


if __name__ == "__main__":
    main()
