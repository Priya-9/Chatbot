"""Retrievers for RAG.

* `BM25Retriever` (default): pure-Python keyword ranking over chunks stored in the database. No extra
  dependencies, no embedding API, works offline - a good default for FAQ-style knowledge bases.
* `ChromaRetriever` (optional): semantic vector search via ChromaDB embeddings. `pip install chromadb`
  and set RAG_BACKEND=chroma.
"""

import logging
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from app.db import session_scope
from app.models import DocumentChunk

log = logging.getLogger(__name__)

# \w plus combining marks used by Indic and Arabic scripts, so words in those scripts are not split apart.
_TOKEN_RE = re.compile(r"[\ẁ-ͯऀ-ॿؐ-ًؚ-ٟ]+", re.UNICODE)


# Small English stopword list; other languages rely on BM25's IDF to down-weight common words.
_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in into is it its me my of on "
    "or our so than that the their them then there these this to us was we what when where which who "
    "why will with you your".split()
)


def _normalize(token: str) -> str:
    # light plural folding for English ("plans" -> "plan", "policies" -> "policy")
    if token.isascii() and len(token) > 3:
        if token.endswith("ies") and len(token) > 4:
            return token[:-3] + "y"
        if token.endswith("s") and not token.endswith("ss"):
            return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [
        _normalize(tok) for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOPWORDS and (len(tok) > 1 or not tok.isascii())
    ]


@dataclass
class Hit:
    source: str
    text: str
    score: float


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[Hit]: ...

    def rebuild(self, chunks: list[tuple[str, str]]) -> None:
        """Re-index from (source, text) pairs."""
        ...


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._lock = threading.Lock()
        self._loaded = False
        self._docs: list[tuple[str, str]] = []
        self._tfs: list[Counter] = []
        self._lengths: list[int] = []
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0

    def _index(self, docs: list[tuple[str, str]]) -> None:
        tfs = [Counter(tokenize(text)) for _, text in docs]
        lengths = [sum(tf.values()) for tf in tfs]
        df: Counter = Counter()
        for tf in tfs:
            df.update(tf.keys())
        n = len(docs)
        self._docs, self._tfs, self._lengths = docs, tfs, lengths
        self._idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}
        self._avgdl = (sum(lengths) / n) if n else 0.0
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            with session_scope() as db:
                rows = db.execute(
                    select(DocumentChunk.source, DocumentChunk.text).order_by(DocumentChunk.id)
                ).all()
            self._index([(r.source, r.text) for r in rows])
            log.info("BM25 index loaded with %d chunks", len(rows))

    def rebuild(self, chunks: list[tuple[str, str]]) -> None:
        with self._lock:
            self._index(chunks)

    def search(self, query: str, k: int) -> list[Hit]:
        self._ensure_loaded()
        terms = [t for t in set(tokenize(query)) if t in self._idf]
        if not terms:
            return []
        scored = []
        for i, tf in enumerate(self._tfs):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * self._lengths[i] / (self._avgdl or 1))
            for term in terms:
                freq = tf.get(term)
                if freq:
                    score += self._idf[term] * freq * (self.k1 + 1) / (freq + norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [Hit(source=self._docs[i][0], text=self._docs[i][1], score=s) for s, i in scored[:k]]


class ChromaRetriever:
    def __init__(self, path: str, collection: str = "knowledge"):
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("RAG_BACKEND=chroma requires `pip install chromadb`") from exc
        self._client = chromadb.PersistentClient(path=path)
        self._name = collection
        self._collection = self._client.get_or_create_collection(collection)

    def rebuild(self, chunks: list[tuple[str, str]]) -> None:
        self._client.delete_collection(self._name)
        self._collection = self._client.get_or_create_collection(self._name)
        if not chunks:
            return
        batch = 500
        for start in range(0, len(chunks), batch):
            part = chunks[start : start + batch]
            self._collection.add(
                ids=[f"c{start + i}" for i in range(len(part))],
                documents=[text for _, text in part],
                metadatas=[{"source": source} for source, _ in part],
            )

    def search(self, query: str, k: int) -> list[Hit]:
        if self._collection.count() == 0:
            return []
        res = self._collection.query(query_texts=[query], n_results=k)
        return [
            Hit(source=meta.get("source", ""), text=doc, score=1.0 - float(dist))
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]
