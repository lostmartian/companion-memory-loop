import json

from companion import config, llm
from companion.store import Store

SUMMARY_SYSTEM = """You compress conversation history into a compact running summary
for an AI companion. Respond with ONLY JSON, no markdown:

{
  "current_state": "who the user is right now: job, relationships, location, situation.
    PRESERVE temporal qualifiers exactly: 'grew up in Porto' must never become
    'lives in Porto'. Past and present states stay separate.",
  "open_threads": ["plans, promises, unresolved topics worth returning to"],
  "emotional_context": "mood, stressors, what the user is processing",
  "last_exchange": "one sentence on what the user and companion last discussed"
}

Rules:
- Merge with any prior summary provided; keep still-relevant old details.
- Never invent information. Never merge two different times, places, or states into one.
- Drop greetings and filler. Keep every section short (1-2 sentences; threads as short items)."""

SUMMARY_KEYS = ["current_state", "open_threads", "emotional_context", "last_exchange"]


def _parse_summary(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return raw.strip()
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return raw.strip()
    if not isinstance(data, dict) or not any(k in data for k in SUMMARY_KEYS):
        return raw.strip()
    lines = []
    if data.get("current_state"):
        lines.append(f"Current state: {data['current_state']}")
    threads = data.get("open_threads") or []
    if threads:
        lines.append("Open threads: " + "; ".join(str(t) for t in threads))
    if data.get("emotional_context"):
        lines.append(f"Emotional context: {data['emotional_context']}")
    if data.get("last_exchange"):
        lines.append(f"Last exchange: {data['last_exchange']}")
    return "\n".join(lines)


def compact_if_needed(store: Store, session_id: str) -> str | None:
    turns = store.get_turns(session_id)
    if len(turns) <= config.RECENT_TURNS:
        summary, _ = store.get_summary(session_id)
        return summary

    recent_ids = {t["id"] for t in turns[-config.RECENT_TURNS :]}
    summary, until_turn = store.get_summary(session_id)
    older = [t for t in turns if t["id"] > until_turn and t["id"] not in recent_ids]
    if not older:
        return summary

    transcript = "\n".join(f"{t['role']}: {t['content']}" for t in older)
    prompt = f"Prior summary:\n{summary or '(none)'}\n\nNew turns to fold in:\n{transcript}\n\nProduce the updated summary JSON."
    raw = llm.generate(
        prompt,
        model=config.UTILITY_MODEL,
        system=SUMMARY_SYSTEM,
        json_mode=True,
        temperature=0.2,
    )
    new_summary = _parse_summary(raw)
    store.set_summary(session_id, new_summary, older[-1]["id"])
    return new_summary
