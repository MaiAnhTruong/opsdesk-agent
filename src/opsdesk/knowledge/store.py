from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeCitation:
    doc_id: str
    chunk_id: str
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class KnowledgeChunk:
    doc_id: str
    chunk_id: str
    title: str
    url: str
    snippet: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    title: str
    url: str
    chunks: tuple[KnowledgeChunk, ...]


class KnowledgeStore:
    def __init__(self, documents: tuple[KnowledgeDocument, ...]) -> None:
        self.documents = documents
        self._chunks = tuple(chunk for doc in documents for chunk in doc.chunks)

    def search(self, query: str, *, limit: int = 3) -> list[dict[str, str]]:
        normalized = query.lower().strip()
        if not normalized:
            return [self._to_citation(chunk) for chunk in self._chunks[:limit]]

        scored: list[tuple[int, KnowledgeChunk]] = []
        for chunk in self._chunks:
            score = 0
            for keyword in chunk.keywords:
                if keyword in normalized:
                    score += 1
            if score:
                scored.append((score, chunk))

        if not scored:
            return [self._to_citation(chunk) for chunk in self._chunks[:limit]]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._to_citation(chunk) for _, chunk in scored[:limit]]

    @staticmethod
    def _to_citation(chunk: KnowledgeChunk) -> dict[str, str]:
        return {
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "url": chunk.url,
            "snippet": chunk.snippet,
        }


def load_default_knowledge_store() -> KnowledgeStore:
    base_dir = Path(__file__).resolve().parents[1]
    data_path = base_dir / "reference_data" / "policies.json"
    if not data_path.exists():
        return KnowledgeStore(_fallback_documents())

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    documents: list[KnowledgeDocument] = []
    for doc in payload:
        chunks = tuple(
            KnowledgeChunk(
                doc_id=str(doc["doc_id"]),
                chunk_id=str(chunk["chunk_id"]),
                title=str(doc["title"]),
                url=str(doc["url"]),
                snippet=str(chunk["snippet"]),
                keywords=tuple(chunk.get("keywords", [])),
            )
            for chunk in doc.get("chunks", [])
        )
        documents.append(
            KnowledgeDocument(
                doc_id=str(doc["doc_id"]),
                title=str(doc["title"]),
                url=str(doc["url"]),
                chunks=chunks,
            )
        )
    return KnowledgeStore(tuple(documents))


def _fallback_documents() -> tuple[KnowledgeDocument, ...]:
    doc = KnowledgeDocument(
        doc_id="policy-generic",
        title="Internal Policy Overview",
        url="https://intranet.example.local/policies",
        chunks=(
            KnowledgeChunk(
                doc_id="policy-generic",
                chunk_id="general-1",
                title="Internal Policy Overview",
                url="https://intranet.example.local/policies",
                snippet="Check the internal policy handbook for detailed guidance.",
                keywords=("policy", "handbook"),
            ),
        ),
    )
    return (doc,)
