from companion import retrieve
from companion.store import Store


def seed(store):
    store.add_fact(
        subject="user", predicate="has_sibling", object="Anna",
        text="User's sister Anna is getting married in June.",
    )
    store.add_fact(
        subject="user", predicate="works_as", object="nurse",
        text="User works as a nurse at the city hospital.",
    )
    store.add_fact(
        subject="user", predicate="dislikes", object="crowded parties",
        text="User hates crowded parties.",
    )


def test_fts_only_path_scores_and_filters(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.vectors.query_similar", lambda *a, **kw: [])
    store = Store(tmp_path / "s.sqlite3")
    seed(store)
    results = retrieve.retrieve(store, "When is Anna's wedding?", k=2)
    assert len(results) >= 1
    top_row, top_score = results[0]
    assert "Anna" in top_row["text"] or "wedding" in top_row["text"]
    assert top_score > 0
    store.close()


def test_vector_fallback_on_error(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("chroma down")

    monkeypatch.setattr("companion.vectors.query_similar", boom)
    store = Store(tmp_path / "s2.sqlite3")
    seed(store)
    results = retrieve.retrieve(store, "nurse", k=3)
    assert len(results) >= 1
    store.close()


def test_retired_facts_never_retrieved(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.vectors.query_similar", lambda *a, **kw: [])
    store = Store(tmp_path / "s3.sqlite3")
    fid = store.add_fact(
        subject="user", predicate="dating", object="Sam", text="User is dating Sam."
    )
    store.retire_fact(fid)
    results = retrieve.retrieve(store, "dating Sam", k=5)
    assert all(row["id"] != fid for row, _ in results)
    store.close()
