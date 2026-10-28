"""Vector store with two backends behind one interface.

* ``ChromaStore``  - ChromaDB (persistent) + sentence-transformers embeddings.
* ``TfidfStore``   - TF-IDF over documents persisted in SQLite. Used when the
  embedding stack is not installed, and in tests.

Collections:
  ``policies`` - enterprise refund policy chunks (cited by decisions)
  ``records``  - customer profiles + cases, metadata ``customer_id`` on every doc

SQLite tables remain the source of truth; ``index_customer`` / ``index_case``
are called after every write so the index stays in sync.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from .config import settings
from .db import Case, Customer, PolicyDocument, RagDocument, mask_account, session_scope

log = logging.getLogger(__name__)


class VectorStore(Protocol):
    backend: str

    def upsert(self, collection: str, doc_id: str, text: str, metadata: dict[str, Any]) -> None: ...
    def delete_where(self, collection: str, where: dict[str, Any]) -> None: ...
    def query(self, collection: str, text: str, k: int = 4,
              where: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...
    def list(self, collection: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


def _matches(meta: dict[str, Any], where: dict[str, Any] | None) -> bool:
    return not where or all(meta.get(k) == v for k, v in where.items())


class TfidfStore:
    backend = "tfidf"

    def upsert(self, collection, doc_id, text, metadata):
        with session_scope() as s:
            row = s.get(RagDocument, (collection, doc_id))
            if row is None:
                s.add(RagDocument(collection=collection, doc_id=doc_id, text=text,
                                  metadata_json=json.dumps(metadata)))
            else:
                row.text, row.metadata_json = text, json.dumps(metadata)

    def delete_where(self, collection, where):
        with session_scope() as s:
            for row in s.query(RagDocument).filter(RagDocument.collection == collection):
                if _matches(json.loads(row.metadata_json), where):
                    s.delete(row)

    def list(self, collection, where=None):
        with session_scope() as s:
            rows = s.query(RagDocument).filter(RagDocument.collection == collection).all()
            docs = [{"id": r.doc_id, "text": r.text, "metadata": json.loads(r.metadata_json)} for r in rows]
        return [d for d in docs if _matches(d["metadata"], where)]

    def query(self, collection, text, k=4, where=None):
        # Filter *before* scoring so out-of-scope documents are never candidates.
        docs = self.list(collection, where)
        if not docs:
            return []
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        try:
            matrix = vec.fit_transform([d["text"] for d in docs] + [text])
        except ValueError:  # empty vocabulary
            return [dict(d, score=0.0) for d in docs[:k]]
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = sorted(zip(scores, range(len(docs))), key=lambda t: (-t[0], t[1]))[:k]
        return [dict(docs[i], score=round(float(sc), 4)) for sc, i in ranked]


class ChromaStore:
    backend = "chroma"

    def __init__(self, path: str):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        self._client = chromadb.PersistentClient(path=path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._ef(["warmup"])  # fail fast here (e.g. model download blocked) -> fallback

    def _col(self, name: str):
        return self._client.get_or_create_collection(name, embedding_function=self._ef,
                                                     metadata={"hnsw:space": "cosine"})

    @staticmethod
    def _where(where):
        if not where:
            return None
        if len(where) == 1:
            return dict(where)
        return {"$and": [{k: v} for k, v in where.items()]}

    def upsert(self, collection, doc_id, text, metadata):
        self._col(collection).upsert(ids=[doc_id], documents=[text], metadatas=[metadata])

    def delete_where(self, collection, where):
        self._col(collection).delete(where=self._where(where))

    def list(self, collection, where=None):
        res = self._col(collection).get(where=self._where(where))
        return [{"id": i, "text": t, "metadata": m}
                for i, t, m in zip(res["ids"], res["documents"], res["metadatas"])]

    def query(self, collection, text, k=4, where=None):
        col = self._col(collection)
        if col.count() == 0:
            return []
        res = col.query(query_texts=[text], n_results=k, where=self._where(where))
        return [{"id": i, "text": t, "metadata": m, "score": round(1 - float(d), 4)}
                for i, t, m, d in zip(res["ids"][0], res["documents"][0],
                                      res["metadatas"][0], res["distances"][0])]


_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    if settings.rag_backend in ("auto", "chroma"):
        try:
            _store = ChromaStore(settings.chroma_dir)
            return _store
        except Exception as exc:  # missing packages, model download blocked, ...
            if settings.rag_backend == "chroma":
                raise
            log.warning("Chroma/embeddings unavailable (%s); using TF-IDF retriever", exc)
    _store = TfidfStore()
    return _store


def reset_store() -> None:
    global _store
    _store = None


# --------------------------------------------------------------------------
# Indexing helpers (called after every write)
# --------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^(#{2,3})\s+(.*)$", re.M)
_REF_RE = re.compile(r"\b(RP-\d+(?:\.\d+)?)\b")


def chunk_policy(name: str, content: str) -> list[tuple[str, str]]:
    """Split a markdown policy at ##/### headings. Chunk id is the section's
    ``RP-x.y`` tag when present, else ``<name>#<n>``."""
    matches = list(_SECTION_RE.finditer(content))
    if not matches:
        return [(f"{name}#0", content.strip())]
    chunks: list[tuple[str, str]] = []
    for n, m in enumerate(matches):
        end = matches[n + 1].start() if n + 1 < len(matches) else len(content)
        body = content[m.start():end].strip()
        ref = _REF_RE.search(m.group(2))
        chunks.append((ref.group(1) if ref else f"{name}#{n}", body))
    return chunks


def index_policy(doc: PolicyDocument) -> list[str]:
    store = get_store()
    store.delete_where("policies", {"source": doc.name})
    ids = []
    for chunk_id, body in chunk_policy(doc.name, doc.content):
        store.upsert("policies", chunk_id, body, {"source": doc.name, "type": "policy"})
        ids.append(chunk_id)
    return ids


def customer_text(c: Customer) -> str:
    return (f"Customer profile #{c.id}: {c.name} <{c.email}>. Bank account {mask_account(c.bank_account)}. "
            f"Balance ${c.balance:.2f}. Notes: {c.notes or 'none'}.")


def case_text(case: Case) -> str:
    return (f"Case #{case.id} ({case.type}) for customer #{case.customer_id}: requested "
            f"${case.amount_requested:.2f}. Status {case.status}. Description: {case.description}")


def index_customer(c: Customer) -> None:
    get_store().upsert("records", f"customer-{c.id}", customer_text(c),
                       {"customer_id": c.id, "type": "customer"})


def index_case(case: Case) -> None:
    get_store().upsert("records", f"case-{case.id}", case_text(case),
                       {"customer_id": case.customer_id, "type": "case", "case_id": case.id})


def reindex_all() -> dict[str, int]:
    with session_scope() as s:
        docs = s.query(PolicyDocument).all()
        customers = s.query(Customer).all()
        cases = s.query(Case).all()
        n_chunks = sum(len(index_policy(d)) for d in docs)
        for c in customers:
            index_customer(c)
        for case in cases:
            index_case(case)
    return {"policy_chunks": n_chunks, "customers": len(customers), "cases": len(cases)}
