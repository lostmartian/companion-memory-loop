import json

import pytest

from companion.ingest import IngestWorker
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


class _ListOut:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(str(args[0]) if args else "")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.vectors._collection", None)
    fake = _FakeCollection()
    monkeypatch.setattr("companion.vectors.get_collection", lambda: fake)
    monkeypatch.setattr("companion.vectors.query_similar", lambda *a, **kw: [])
    calls = {"n": 0}

    def canned(*args, **kwargs):
        calls["n"] += 1
        predicate = "likes" if calls["n"] == 1 else "dislikes"
        verb = "likes" if calls["n"] == 1 else "hates"
        return json.dumps(
            [
                {
                    "subject": "user",
                    "predicate": predicate,
                    "object": "rain",
                    "text": f"User {verb} rain.",
                }
            ]
        )

    monkeypatch.setattr("companion.extract.llm.generate", canned)
    return tmp_path, fake


def test_worker_stores_facts_off_thread(env):
    tmp_path, fake = env
    out = _ListOut()
    worker = IngestWorker(tmp_path / "ingest.sqlite3", out)
    worker.submit("I like rain", "", 1)
    worker.submit("I like rain a lot", "", 2)
    worker.flush()
    worker.stop()

    store = Store(tmp_path / "ingest.sqlite3")
    assert len(store.get_active()) == 2
    store.close()
    assert any("memory (NEW)" in line for line in out.lines)


def test_worker_stop_without_tasks(env):
    tmp_path, _ = env
    worker = IngestWorker(tmp_path / "idle.sqlite3", _ListOut())
    worker.flush()
    worker.stop()
    store = Store(tmp_path / "idle.sqlite3")
    assert store.get_active() == []
    store.close()


def test_worker_survives_processing_error(env, monkeypatch):
    tmp_path, _ = env

    def bad_first(*args, **kwargs):
        raise RuntimeError("llm exploded")

    out = _ListOut()
    worker = IngestWorker(tmp_path / "err.sqlite3", out)
    monkeypatch.setattr("companion.extract.extract_facts", bad_first)
    worker.submit("first message", "", 1)
    worker.flush()

    monkeypatch.setattr("companion.extract.extract_facts", lambda *a, **kw: [])
    worker.submit("second message", "", 2)
    worker.flush()
    worker.stop()
    assert any("ingest error" in line for line in out.lines)
