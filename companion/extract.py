import json

from companion import config, llm, vectors
from companion.persona import is_companion_owned
from companion.schema import Fact
from companion.store import Store

EXTRACTION_SYSTEM = """You extract durable, memory-worthy facts from conversations
for an AI companion's long-term memory.

Extract ONLY durable personal disclosures: relationships, work, studies, where someone
lives, pets, plans, important events, stable preferences, strong opinions.

Do NOT extract: small talk, transient states ("I'm tired today"), questions, things the
user asks the companion, hypotheticals, jokes, or anything about the companion's persona.

Subject registry (strict):
- subject MUST be "user" for anything about the person being talked to.
- Use a named third party only when the statement is primarily about that person
  (e.g. "Anna is getting married").
- The COMPANION is a separate persona (named Milo, with a dog named Biscuit). Facts
  about the companion must NEVER be extracted as user facts: subject or possessed
  object must never be the companion, the companion's dog, or the companion's belongings.

Rules:
- predicate: snake_case relation, e.g. works_as, lives_in, has_pet, dating, broke_up_with,
  has_sibling, likes, dislikes, plans_to, attends, has_opinion.
- object: short value, e.g. "nurse", "Lisbon", "June wedding".
- text: one complete third-person sentence that stands alone with full context,
  e.g. "User works as a nurse at a city hospital."
- Resolve pronouns using recent conversation (she -> Anna).
- category: one of relationship, work, preference, plan, event, opinion, other.
- entities: names of people/places/things mentioned.
- search_keys: 3-6 short phrases a person might later use to recall this fact
  (synonyms, related terms, natural questions, e.g. for a wedding fact:
  ["when is anna's wedding", "wedding date", "june event", "lisbon trip"]).
- confidence: 1.0 for explicit statements, lower for inferences.
- Return [] if nothing durable was said. Never invent facts.

Respond with ONLY a JSON array. No markdown, no commentary."""


def parse_facts(raw: str) -> list[Fact]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("facts", [])
    facts = []
    for item in data if isinstance(data, list) else []:
        try:
            facts.append(Fact.model_validate(item))
        except Exception:
            continue
    return facts


def validate_subjects(facts: list[Fact]) -> tuple[list[Fact], list[Fact]]:
    kept, dropped = [], []
    for fact in facts:
        if is_companion_owned(fact.subject, fact.predicate, fact.object):
            dropped.append(fact)
        else:
            kept.append(fact)
    return kept, dropped


def extract_facts(user_message: str, recent_context: str = "") -> list[Fact]:
    prompt = (
        f"Recent conversation:\n{recent_context}\n\n"
        f"Latest user message:\n{user_message}\n\n"
        "Extract memory-worthy facts as a JSON array."
    )
    raw = llm.generate(
        prompt,
        model=config.UTILITY_MODEL,
        system=EXTRACTION_SYSTEM,
        json_mode=True,
        temperature=0.1,
    )
    facts = parse_facts(raw)
    kept, _ = validate_subjects(facts)
    return kept


def fact_embed_text(fact: Fact) -> str:
    if fact.search_keys:
        return f"{fact.text}. Related: {', '.join(fact.search_keys)}"
    return fact.text


def commit_fact(store: Store, fact: Fact, source_turn: int | None = None) -> int:
    fact_id = store.add_fact(
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        text=fact.text,
        category=fact.category,
        entities=fact.entities,
        confidence=fact.confidence,
        keywords=fact.search_keys,
        source_turn=source_turn,
    )
    vectors.upsert_fact(
        fact_id,
        fact.text,
        metadata={"status": "active", "subject": fact.subject, "category": fact.category},
        embed_text=fact_embed_text(fact),
    )
    return fact_id
