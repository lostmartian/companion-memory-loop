import json

import pytest

from companion import extract
from companion.schema import Fact
from companion.store import Store


@pytest.fixture()
def store(tmp_path, monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr("companion.vectors._collection", None)
    monkeypatch.setattr("companion.vectors.get_collection", lambda: fake)
    s = Store(tmp_path / "extract.sqlite3")
    yield s
    s.close()


class _FakeCollection:
    def __init__(self):
        self.items = {}

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, doc in zip(ids, documents):
            self.items[i] = doc

    def delete(self, ids):
        for i in ids:
            self.items.pop(i, None)


def canned(mock_raw):
    def fake_generate(*args, **kwargs):
        return json.dumps(mock_raw)

    return fake_generate


def test_parse_facts_valid_array():
    raw = json.dumps(
        [
            {
                "subject": "user",
                "predicate": "works_as",
                "object": "nurse",
                "text": "User works as a nurse.",
                "category": "work",
                "entities": ["nurse"],
                "confidence": 1.0,
            }
        ]
    )
    facts = extract.parse_facts(raw)
    assert len(facts) == 1
    assert isinstance(facts[0], Fact)
    assert facts[0].predicate == "works_as"


def test_parse_facts_malformed_returns_empty():
    assert extract.parse_facts("not json at all") == []
    assert extract.parse_facts('{"broken": true') == []


def test_parse_facts_skips_invalid_items():
    raw = json.dumps([{"subject": "user"}, "garbage", {"object": "x"}])
    assert extract.parse_facts(raw) == []


def test_parse_facts_accepts_object_wrapper():
    raw = json.dumps(
        {
            "facts": [
                {
                    "subject": "user",
                    "predicate": "likes",
                    "object": "rain",
                    "text": "User likes rain.",
                }
            ]
        }
    )
    assert len(extract.parse_facts(raw)) == 1


def test_extract_facts_calls_llm_and_parses(store, monkeypatch):
    monkeypatch.setattr(
        "companion.extract.llm.generate",
        canned(
            [
                {
                    "subject": "user",
                    "predicate": "has_sibling",
                    "object": "Anna",
                    "text": "User's sister Anna is getting married in June.",
                    "category": "relationship",
                    "entities": ["Anna"],
                    "confidence": 1.0,
                }
            ]
        ),
    )
    facts = extract.extract_facts("my sister Anna is getting married in June!")
    assert len(facts) == 1
    fid = extract.commit_fact(store, facts[0], source_turn=1)
    row = store.get_fact(fid)
    assert row["object"] == "Anna"
    from companion import vectors

    assert str(fid) in vectors.get_collection().items


def test_commit_fact_writes_both_stores(store, monkeypatch):
    monkeypatch.setattr(
        "companion.extract.llm.generate",
        canned(
            [
                {
                    "subject": "user",
                    "predicate": "works_as",
                    "object": "nurse",
                    "text": "User works as a nurse.",
                    "category": "work",
                    "entities": ["nurse"],
                    "confidence": 1.0,
                }
            ]
        ),
    )
    facts = extract.extract_facts("I've been a nurse for three years")
    fid = extract.commit_fact(store, facts[0])
    assert store.get_active()[0]["id"] == fid
