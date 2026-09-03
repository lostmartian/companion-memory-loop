import chromadb
from google.genai import types

from companion import config
from companion.llm import get_client

_collection: chromadb.Collection | None = None


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
        _collection = client.get_or_create_collection(
            name=config.FACT_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    response = get_client().models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=config.EMBEDDING_DIMENSIONS,
        ),
    )
    return [list(e.values) for e in response.embeddings]


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    return _embed([text], "RETRIEVAL_QUERY")[0]


def upsert_fact(
    fact_id: int, text: str, metadata: dict | None = None, embed_text: str | None = None
) -> None:
    collection = get_collection()
    embedding = embed_documents([embed_text or text])[0]
    collection.upsert(
        ids=[str(fact_id)],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata or {"status": "active"}],
    )


def delete_fact(fact_id: int) -> None:
    get_collection().delete(ids=[str(fact_id)])


def query_similar(text: str, k: int = 5) -> list[tuple[int, float]]:
    response = get_collection().query(
        query_embeddings=[embed_query(text)],
        n_results=k,
        include=["distances"],
    )
    ids = response["ids"][0]
    distances = response["distances"][0]
    return [(int(fid), float(d)) for fid, d in zip(ids, distances)]


def reset_collection(name: str | None = None) -> None:
    global _collection
    target = name or config.FACT_COLLECTION
    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    if target in [c.name for c in client.list_collections()]:
        client.delete_collection(target)
    _collection = None


def rebuild_from_store(store) -> int:
    reset_collection()
    rows = store.get_active()
    if not rows:
        return 0
    texts = [r["text"] for r in rows]
    embeddings = embed_documents(texts)
    get_collection().upsert(
        ids=[str(r["id"]) for r in rows],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {"status": "active", "subject": r["subject"], "category": r["category"]}
            for r in rows
        ],
    )
    return len(rows)
