import json
import sqlite3

import pytest

from companion.store import Store, utcnow

OLD_SCHEMA = """
CREATE TABLE facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    entities TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by INTEGER,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    source_turn INTEGER
);
CREATE VIRTUAL TABLE fts_facts USING fts5(
    text, subject, predicate, object, content='facts', content_rowid='id'
);
CREATE TRIGGER facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO fts_facts(rowid, text, subject, predicate, object)
    VALUES (new.id, new.text, new.subject, new.predicate, new.object);
END;
"""


def test_migration_adds_keywords_and_rebuilds_fts(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO facts (subject, predicate, object, text, valid_from, observed_at, recorded_at)"
        " VALUES ('user', 'has_sibling', 'Anna', 'Anna is the sister of the user.', ?, ?, ?)",
        (utcnow(), utcnow(), utcnow()),
    )
    conn.commit()
    conn.close()

    store = Store(path)
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(facts)")}
    assert "keywords" in cols
    hits = store.search_fts("sister")
    assert len(hits) == 1

    fid = store.add_fact(
        subject="user",
        predicate="has_event",
        object="June 14th",
        text="Anna's big day is set.",
        keywords=["when is anna's wedding", "wedding date"],
    )
    hits = store.search_fts("wedding")
    assert fid in [r["id"] for r in hits]
    store.close()
