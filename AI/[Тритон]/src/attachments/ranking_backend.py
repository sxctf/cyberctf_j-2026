# ============================================================================
# Extracted model handler: ranking_backend.
# Provided for read-only source review in CTF. Not compiled by the service.
# This model handles structured JSON fields and bounded text scoring.
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RankRequest:
    query: str
    documents: list[str]
    top_k: int


def infer(payload: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    request = _parse_request(payload, parameters or {})
    query_terms = _terms(request.query)

    scored = []
    for index, document in enumerate(request.documents):
        score = _score_document(query_terms, document)
        scored.append({"index": index, "score": score})

    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = scored[: request.top_k]

    return {
        "model_name": "ranking_backend",
        "outputs": [
            {
                "name": "scores",
                "datatype": "FP32",
                "shape": [len(selected)],
                "data": [item["score"] for item in selected],
            },
            {
                "name": "indices",
                "datatype": "INT64",
                "shape": [len(selected)],
                "data": [item["index"] for item in selected],
            },
        ],
    }


def _parse_request(payload: dict[str, Any], parameters: dict[str, Any]) -> RankRequest:
    query = str(payload.get("query", ""))
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        documents = [str(documents)]

    top_k = int(parameters.get("top_k", payload.get("top_k", len(documents) or 1)))
    top_k = max(1, min(top_k, len(documents) or 1))

    return RankRequest(
        query=query,
        documents=[str(document)[:2048] for document in documents],
        top_k=top_k,
    )


def _terms(text: str) -> set[str]:
    return {term for term in text.lower().split() if term}


def _score_document(query_terms: set[str], document: str) -> float:
    document_terms = _terms(document)
    if not query_terms:
        return 0.0

    overlap = len(query_terms & document_terms)
    coverage = overlap / len(query_terms)
    density = overlap / max(1, len(document_terms))
    return round((coverage * 0.8) + (density * 0.2), 6)
