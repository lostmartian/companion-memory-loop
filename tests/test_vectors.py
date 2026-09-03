import pytest

from companion import config, vectors


@pytest.fixture(scope="module", autouse=True)
def isolated_collection():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config, "FACT_COLLECTION", "test_facts")
    vectors.reset_collection()
    yield
    vectors.reset_collection()
    monkey.undo()


def test_embed_dimensions():
    embs = vectors.embed_documents(["hello world", "goodbye world"])
    assert len(embs) == 2
    assert all(len(e) == 768 for e in embs)


def test_task_type_split():
    doc = vectors.embed_documents(["User likes rainy nights"])[0]
    query = vectors.embed_query("what does the user like?")
    assert len(doc) == len(query) == 768


def test_upsert_query_delete_roundtrip():
    vectors.upsert_fact(900001, "User's sister Anna is getting married in June.")
    vectors.upsert_fact(900002, "User dislikes crowded concerts.")
    hits = vectors.query_similar("When is the user's sister's wedding?", k=2)
    assert hits[0][0] == 900001

    vectors.delete_fact(900001)
    vectors.delete_fact(900002)
    hits = vectors.query_similar("sister wedding", k=2)
    assert 900001 not in [h[0] for h in hits]
