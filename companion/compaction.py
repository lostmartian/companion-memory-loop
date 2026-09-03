from companion import config, llm
from companion.store import Store

SUMMARY_SYSTEM = """You compress conversation history into a compact running summary
for an AI companion.

Write a short third-person narrative (under 150 words) covering:
- what is happening in the user's life (work, relationships, events, stress)
- emotional context and tone
- promises, plans, or open threads ("user wants to ask about X")
- what the companion last said or offered

Merge with any prior summary provided; keep still-relevant old details, drop
greetings and filler. Never invent information. Plain prose, no lists."""


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
    prompt = f"Prior summary:\n{summary or '(none)'}\n\nNew turns to fold in:\n{transcript}\n\nProduce the updated summary."
    new_summary = llm.generate(
        prompt,
        model=config.UTILITY_MODEL,
        system=SUMMARY_SYSTEM,
        temperature=0.2,
    ).strip()
    store.set_summary(session_id, new_summary, older[-1]["id"])
    return new_summary
