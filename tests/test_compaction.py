import json

import pytest

from companion import compaction
from companion.store import Store


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = Store(tmp_path / "compact.sqlite3")
    yield s
    s.close()


def canned_summary(text):
    def fake_generate(*args, **kwargs):
        return text

    return fake_generate


def test_no_compaction_under_threshold(store):
    store.add_turn("s", "user", "hi")
    store.add_turn("s", "assistant", "hello")
    assert compaction.compact_if_needed(store, "s") is None


def test_compacts_turns_older_than_window(store, monkeypatch):
    monkeypatch.setattr(
        "companion.compaction.llm.generate",
        canned_summary("User had a long hospital shift and talked about sister Anna's wedding."),
    )
    for i in range(14):
        store.add_turn("s", "user" if i % 2 == 0 else "assistant", f"msg {i}")
    summary = compaction.compact_if_needed(store, "s")
    assert summary is not None
    assert "Anna" in summary
    stored, until = store.get_summary("s")
    assert stored == summary
    turns = store.get_turns("s")
    recent_ids = {t["id"] for t in turns[-8:]}
    assert until not in recent_ids


def test_second_compaction_only_folds_new_turns(store, monkeypatch):
    calls = []

    def fake_generate(prompt, *args, **kwargs):
        calls.append(prompt)
        return f"summary v{len(calls)}"

    monkeypatch.setattr("companion.compaction.llm.generate", fake_generate)
    for i in range(10):
        store.add_turn("s", "user" if i % 2 == 0 else "assistant", f"msg {i}")
    compaction.compact_if_needed(store, "s")
    assert len(calls) == 1

    store.add_turn("s", "user", "new message")
    store.add_turn("s", "assistant", "reply")
    store.add_turn("s", "user", "another")
    store.add_turn("s", "assistant", "more")
    compaction.compact_if_needed(store, "s")
    assert len(calls) == 2
    assert "summary v1" in calls[1]
    assert "msg 0" not in calls[1]


def test_no_summary_call_when_only_recent_turns(store, monkeypatch):
    calls = []

    def fake_generate(*args, **kwargs):
        calls.append(1)
        return "s"

    monkeypatch.setattr("companion.compaction.llm.generate", fake_generate)
    for i in range(8):
        store.add_turn("s", "user" if i % 2 == 0 else "assistant", f"m{i}")
    compaction.compact_if_needed(store, "s")
    assert calls == []
