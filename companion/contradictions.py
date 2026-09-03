import json

from companion import config, extract, llm, vectors
from companion.schema import Fact
from companion.store import Store

CLASSIFIER_SYSTEM = """You maintain a long-term memory store for an AI companion.
You are given a NEW FACT and EXISTING FACTS already stored about the same person.

For EACH existing fact, decide its relation to the new fact:
- "DUPLICATE": it expresses the same information as the new fact (wording may differ).
- "SUPERSEDES": the new fact replaces it — the older statement is no longer true
  (changed job, moved city, broke up, got married, changed plans, or the new fact is a
  strictly more detailed/corrected version of the same fact).
- "UNRELATED": different information; both can coexist.

Rules:
- Judge information, not wording. "I broke up with Sam" SUPERSEDES "User is dating Sam".
- "User works as a nurse" vs "User works as a nurse at city hospital" — the more detailed
  one SUPERSEDES the vaguer one if stored; otherwise they are DUPLICATE-level info.
- RECOUNTS ARE NOT NEW STATES: if the new fact recalls, asks about, or re-tells something
  already known ("like I said, I dated Sam", "remember my breakup"), it is DUPLICATE of
  the matching stored fact when consistent with it, and UNRELATED otherwise. Only
  present-tense announcements of a new state supersede ("Sam and I broke up" after
  dating facts; "I switched to day shifts" after night-shift facts).
- When in doubt between DUPLICATE and UNRELATED, choose DUPLICATE only if a person reading
  both would learn nothing new from the second one.
- Never invent ids. Only judge ids from the EXISTING FACTS list.

Respond with ONLY JSON: {"verdicts": [{"id": <int>, "relation": "DUPLICATE|SUPERSEDES|UNRELATED"}]}"""


def classify_candidates(new_fact: Fact, candidates: list) -> dict[int, str]:
    if not candidates:
        return {}
    listing = "\n".join(f"[{r['id']}] {r['text']}" for r in candidates)
    prompt = (
        f"NEW FACT: {new_fact.text} "
        f"(subject={new_fact.subject}, predicate={new_fact.predicate}, object={new_fact.object})\n\n"
        f"EXISTING FACTS:\n{listing}\n\n"
        "Return the verdict JSON."
    )
    raw = llm.generate(
        prompt,
        model=config.UTILITY_MODEL,
        system=CLASSIFIER_SYSTEM,
        json_mode=True,
        temperature=0.0,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return {}
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return {}
    verdicts = {}
    for v in data.get("verdicts", []):
        try:
            verdicts[int(v["id"])] = str(v["relation"]).upper()
        except (KeyError, TypeError, ValueError):
            continue
    return verdicts


def find_candidates(store: Store, new_fact: Fact, k: int = 3) -> list:
    candidate_ids: list[int] = []
    try:
        candidate_ids += [fid for fid, _ in vectors.query_similar(new_fact.text, k=k)]
    except Exception:
        pass
    candidate_ids += [r["id"] for r in store.similar_active(new_fact.subject, new_fact.predicate)]
    seen, unique = set(), []
    for fid in candidate_ids:
        if fid not in seen:
            seen.add(fid)
            row = store.get_fact(fid)
            if row is not None and row["status"] == "active":
                unique.append(row)
    return unique


QUESTION_STARTERS = (
    "what ", "when ", "where ", "who ", "why ", "how ", "do i ", "did i ", "am i ",
    "is my ", "was i ", "can you remind", "remember",
)


def looks_like_recount(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered.endswith("?"):
        return True
    return any(lowered.startswith(s) for s in QUESTION_STARTERS)


def process_fact(store: Store, fact: Fact, source_turn: int | None = None) -> str:
    if looks_like_recount(fact.text):
        return "SKIPPED_RECOUNT"

    candidates = find_candidates(store, fact)
    if not candidates:
        extract.commit_fact(store, fact, source_turn=source_turn)
        return "NEW"

    verdicts = classify_candidates(fact, candidates)
    superseded_ids = [fid for fid, rel in verdicts.items() if rel == "SUPERSEDES"]
    has_duplicate = any(rel == "DUPLICATE" for rel in verdicts.values())

    if superseded_ids:
        new_id = extract.commit_fact(store, fact, source_turn=source_turn)
        for old_id in superseded_ids:
            store.retire_fact(old_id, superseded_by=new_id)
            vectors.delete_fact(old_id)
        return "SUPERSEDES"
    if has_duplicate:
        return "DUPLICATE"

    extract.commit_fact(store, fact, source_turn=source_turn)
    return "NEW"
