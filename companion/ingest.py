import queue
import threading
from pathlib import Path

from companion import extract
from companion.contradictions import process_fact
from companion.store import Store


class IngestWorker:
    """Per-session background memory ingestion.

    Owns its own SQLite connection (single worker thread per session keeps write
    ordering deterministic). The chat turn returns immediately after the reply;
    extraction + contradiction classification happen off the reply path.
    """

    def __init__(self, db_path: Path, out):
        self.db_path = Path(db_path)
        self.out = out
        self.q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, user_message: str, recent_context: str, source_turn: int) -> None:
        self.q.put((user_message, recent_context, source_turn))

    def flush(self) -> None:
        self.q.join()

    def stop(self) -> None:
        self.q.put(None)
        self._thread.join(timeout=10)

    def _run(self) -> None:
        store = Store(self.db_path)
        try:
            while True:
                task = self.q.get()
                if task is None:
                    break
                message, context, source_turn = task
                try:
                    facts = extract.extract_facts(message, recent_context=context)
                    for fact in facts:
                        action = process_fact(store, fact, source_turn=source_turn)
                        self.out.print(f"  [dim]memory ({action}): {fact.text}[/dim]")
                except Exception as e:
                    self.out.print(f"  [red]ingest error: {e}[/red]")
                finally:
                    self.q.task_done()
        finally:
            store.close()
