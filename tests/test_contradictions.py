import json

import pytest

from companion import contradictions
from companion.schema import Fact
from companion.store import Store


class _FakeCollection:
    def __init__(self):
        self.items = set()

    def upsert(self, ids, embeddings, documents, metadatas):
        self.items.update(ids)

    def delete(self, ids):
        for i in ids:
            self.items.discard(i)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr("companion.vectors._collection", None)
    monkeypatch.setattr("companion.vectors.get_collection", lambda: fake)
    monkeypatch.setattr("companion.vectors.query_similar", lambda *a, **kw: [])
    s = Store(tmp_path / "contra.sqlite3")
    yield s, fake
    s.close()


def fact(text="User is dating Sam.", predicate="in_relationship_with", obj="Sam"):
    return Fact(
        subject="user",
        predicate=predicate,
        object=obj,
        text=text,
        category="relationship",
    )


def canned_verdicts(verdicts):
    def fake_generate(*args, **kwargs):
        return json.dumps({"verdicts": verdicts})

    return fake_generate


def test_new_fact_no_candidates(store):
    s, fake = store
    action = contradictions.process_fact(s, fact())
    assert action == "NEW"
    assert len(s.get_active()) == 1
    assert str(s.get_active()[0]["id"]) in fake.items


def test_supersedes_retires_old_and_deletes_vector(store, monkeypatch):
    s, fake = store
    assert contradictions.process_fact(s, fact()) == "NEW"
    rows = s.get_active()
    old_fid = rows[0]["id"]

    monkeypatch.setattr(
        "companion.contradictions.llm.generate",
        canned_verdicts([{"id": old_fid, "relation": "SUPERSEDES"}]),
    )
    monkeypatch.setattr(
        "companion.vectors.query_similar",
        lambda *a, **kw: [(old_fid, 0.1)],
    )
    action = contradictions.process_fact(s, fact("User broke up with Sam."))
    assert action == "SUPERSEDES"

    active = s.get_active()
    assert len(active) == 1
    assert "broke up" in active[0]["text"]
    retired = s.get_fact(old_fid)
    assert retired["status"] == "retired"
    assert retired["superseded_by"] == active[0]["id"]
    assert retired["valid_to"] is not None
    assert str(old_fid) not in fake.items


def test_duplicate_skips_store(store, monkeypatch):
    s, fake = store
    contradictions.process_fact(s, fact())
    old_fid = s.get_active()[0]["id"]

    monkeypatch.setattr(
        "companion.contradictions.llm.generate",
        canned_verdicts([{"id": old_fid, "relation": "DUPLICATE"}]),
    )
    monkeypatch.setattr(
        "companion.vectors.query_similar",
        lambda *a, **kw: [(old_fid, 0.05)],
    )
    action = contradictions.process_fact(s, fact("User is in a relationship with Sam."))
    assert action == "DUPLICATE"
    assert len(s.get_active()) == 1


def test_unrelated_stores_both(store, monkeypatch):
    s, fake = store
    contradictions.process_fact(s, fact())
    old_fid = s.get_active()[0]["id"]

    monkeypatch.setattr(
        "companion.contradictions.llm.generate",
        canned_verdicts([{"id": old_fid, "relation": "UNRELATED"}]),
    )
    monkeypatch.setattr(
        "companion.vectors.query_similar",
        lambda *a, **kw: [(old_fid, 0.4)],
    )
    action = contradictions.process_fact(
        s, fact("User adopted a dog named Biscuit.", predicate="has_pet", obj="Biscuit")
    )
    assert action == "NEW"
    assert len(s.get_active()) == 2


def test_malformed_verdict_defaults_to_new(store, monkeypatch):
    s, fake = store
    contradictions.process_fact(s, fact())
    old_fid = s.get_active()[0]["id"]

    def bad_generate(*args, **kwargs):
        return "not json { at all"

    monkeypatch.setattr("companion.contradictions.llm.generate", bad_generate)
    monkeypatch.setattr(
        "companion.vectors.query_similar", lambda *a, **kw: [(old_fid, 0.1)]
    )
    action = contradictions.process_fact(s, fact("User moved to Lisbon."))
    assert action == "NEW"
    assert len(s.get_active()) == 2


def test_recount_question_skipped_without_llm(store, monkeypatch):
    s, fake = store
    contradictions.process_fact(s, fact())
    fid = s.get_active()[0]["id"]

    def explode(*args, **kwargs):
        raise AssertionError("classifier should not run for recounts")

    monkeypatch.setattr("companion.contradictions.llm.generate", explode)
    monkeypatch.setattr(
        "companion.vectors.query_similar", lambda *a, **kw: [(fid, 0.1)]
    )

    assert contradictions.process_fact(s, fact("Did I mention I am dating Sam?")) == "SKIPPED_RECOUNT"
    assert contradictions.process_fact(s, fact("Remember I dated Sam?")) == "SKIPPED_RECOUNT"
    assert len(s.get_active()) == 1
