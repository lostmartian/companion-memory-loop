import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
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
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject, predicate);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    summarized_until_turn INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_facts USING fts5(
    text, subject, predicate, object, content='facts', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO fts_facts(rowid, text, subject, predicate, object)
    VALUES (new.id, new.text, new.subject, new.predicate, new.object);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO fts_facts(fts_facts, rowid, text, subject, predicate, object)
    VALUES ('delete', old.id, old.text, old.subject, old.predicate, old.object);
END;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def add_fact(
        self,
        *,
        subject: str,
        predicate: str,
        object: str,
        text: str,
        category: str = "other",
        entities: list[str] | None = None,
        confidence: float = 1.0,
        observed_at: str | None = None,
        source_turn: int | None = None,
    ) -> int:
        now = utcnow()
        cur = self.conn.execute(
            """
            INSERT INTO facts (
                subject, predicate, object, text, category, entities, confidence,
                valid_from, valid_to, status, superseded_by, observed_at, recorded_at, source_turn
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'active', NULL, ?, ?, ?)
            """,
            (
                subject,
                predicate,
                object,
                text,
                category,
                json.dumps(entities or []),
                confidence,
                observed_at or now,
                now,
                now,
                source_turn,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_fact(self, fact_id: int) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return row

    def retire_fact(self, fact_id: int, superseded_by: int | None = None) -> None:
        self.conn.execute(
            """
            UPDATE facts
            SET status = 'retired', valid_to = ?, superseded_by = ?
            WHERE id = ? AND status = 'active'
            """,
            (utcnow(), superseded_by, fact_id),
        )
        self.conn.commit()

    def get_active(self, subject: str | None = None) -> list[sqlite3.Row]:
        if subject:
            rows = self.conn.execute(
                "SELECT * FROM facts WHERE status = 'active' AND subject = ? ORDER BY id",
                (subject,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM facts WHERE status = 'active' ORDER BY id"
            ).fetchall()
        return rows

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = [t for t in query.split() if any(ch.isalnum() for ch in t)]
        if not tokens:
            return '""'
        return " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)

    def search_fts(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT f.* FROM fts_facts ft
            JOIN facts f ON f.id = ft.rowid
            WHERE fts_facts MATCH ? AND f.status = 'active'
            ORDER BY rank
            LIMIT ?
            """,
            (self._fts_query(query), limit),
        ).fetchall()
        return rows

    def similar_active(
        self, subject: str, predicate: str, limit: int = 5
    ) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT * FROM facts
            WHERE status = 'active' AND subject = ? AND predicate = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (subject, predicate, limit),
        ).fetchall()
        return rows

    def add_turn(self, session_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_turns(self, session_id: str, limit: int | None = None) -> list[sqlite3.Row]:
        if limit is None:
            rows = self.conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?
                ) ORDER BY id
                """,
                (session_id, limit),
            ).fetchall()
        return rows

    def count_turns(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row["n"])

    def set_summary(self, session_id: str, summary: str, until_turn: int) -> None:
        self.conn.execute(
            """
            INSERT INTO session_summaries (session_id, summary, summarized_until_turn, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = excluded.summary,
                summarized_until_turn = excluded.summarized_until_turn,
                updated_at = excluded.updated_at
            """,
            (session_id, summary, until_turn, utcnow()),
        )
        self.conn.commit()

    def get_summary(self, session_id: str) -> tuple[str | None, int]:
        row = self.conn.execute(
            "SELECT summary, summarized_until_turn FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None, 0
        return row["summary"], int(row["summarized_until_turn"])
