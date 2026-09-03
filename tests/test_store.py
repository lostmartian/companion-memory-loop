import sqlite3

import pytest

from companion.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "test.sqlite3")
    yield s
    s.close()


def test_add_and_get_active(store):
    fid = store.add_fact(
        subject="user",
        predicate="works_as",
        object="nurse",
        text="User works as a nurse.",
        category="work",
        entities=["nurse"],
    )
    active = store.get_active()
    assert len(active) == 1
    assert active[0]["id"] == fid
    assert active[0]["object"] == "nurse"
    assert active[0]["status"] == "active"
    assert active[0]["valid_to"] is None


def test_retire_supersedes(store):
    old_id = store.add_fact(
        subject="user",
        predicate="in_relationship_with",
        object="Sam",
        text="User is dating Sam.",
        category="relationship",
    )
    new_id = store.add_fact(
        subject="user",
        predicate="in_relationship_with",
        object="nobody",
        text="User broke up with Sam.",
        category="relationship",
    )
    store.retire_fact(old_id, superseded_by=new_id)
    retired = store.get_fact(old_id)
    assert retired["status"] == "retired"
    assert retired["valid_to"] is not None
    assert retired["superseded_by"] == new_id
    active = store.get_active()
    assert [r["id"] for r in active] == [new_id]


def test_get_active_subject_filter(store):
    store.add_fact(
        subject="user", predicate="likes", object="coffee", text="User likes coffee."
    )
    store.add_fact(
        subject="persona",
        predicate="has_pet",
        object="Biscuit",
        text="Milo has a dog named Biscuit.",
    )
    assert len(store.get_active(subject="user")) == 1
    assert len(store.get_active(subject="persona")) == 1


def test_fts_search_active_only(store):
    store.add_fact(
        subject="user",
        predicate="has_sister",
        object="Anna",
        text="User's sister Anna is getting married in June.",
        entities=["Anna"],
    )
    store.add_fact(
        subject="user",
        predicate="dislikes",
        object="crowds",
        text="User dislikes crowded concerts.",
    )
    hits = store.search_fts("sister married")
    assert len(hits) == 1
    assert hits[0]["object"] == "Anna"

    store.retire_fact(hits[0]["id"])
    assert store.search_fts("sister married") == []


def test_similar_active(store):
    a = store.add_fact(
        subject="user", predicate="in_relationship_with", object="Sam", text="dating Sam"
    )
    store.add_fact(
        subject="user", predicate="works_as", object="nurse", text="works as nurse"
    )
    rows = store.similar_active("user", "in_relationship_with")
    assert [r["id"] for r in rows] == [a]


def test_turns_roundtrip(store):
    store.add_turn("s1", "user", "hello")
    store.add_turn("s1", "assistant", "hi there")
    store.add_turn("s2", "user", "other session")
    rows = store.get_turns("s1")
    assert [r["role"] for r in rows] == ["user", "assistant"]
    last = store.get_turns("s1", limit=1)
    assert last[0]["content"] == "hi there"
    assert store.count_turns("s1") == 2


def test_persistence_across_connections(tmp_path):
    path = tmp_path / "persist.sqlite3"
    s1 = Store(path)
    fid = s1.add_fact(
        subject="user", predicate="likes", object="rain", text="User likes rain."
    )
    s1.close()
    s2 = Store(path)
    assert s2.get_fact(fid)["object"] == "rain"
    s2.close()


def test_entities_stored_as_json(store):
    fid = store.add_fact(
        subject="user",
        predicate="has_pet",
        object="Biscuit",
        text="User has a dog named Biscuit.",
        entities=["Biscuit", "dog"],
    )
    import json

    row = store.get_fact(fid)
    assert json.loads(row["entities"]) == ["Biscuit", "dog"]
