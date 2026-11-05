from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from app.services import state_store


@dataclass(frozen=True)
class ServiceResponse:
    body: dict[str, Any]
    status_code: int = 200


MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "vision_embedder",
        "version": "1.5.0",
        "backend": "onnxruntime",
        "state": "READY",
        "description": "Стабильный маршрут embedding с жесткими границами tensor.",
        "shared_memory_fast_path": False,
        "inputs": [{"name": "pixels", "datatype": "FP32", "shape": [-1]}],
        "outputs": [{"name": "embedding", "datatype": "FP32", "shape": [4]}],
    },
    {
        "name": "ranking_backend",
        "version": "2.2.0",
        "backend": "python",
        "state": "READY",
        "description": "Внутренний сервис ранжирования поиска с ограниченным парсингом запросов.",
        "shared_memory_fast_path": False,
        "inputs": [{"name": "query", "datatype": "BYTES"}, {"name": "documents", "datatype": "BYTES"}],
        "outputs": [{"name": "scores", "datatype": "FP32", "shape": [-1]}],
    },
    {
        "name": "stateful_python_backend",
        "version": "24.02-legacy",
        "backend": "triton_python_backend",
        "state": "READY",
        "description": "Устаревший stateful Python backend, который всё ещё принимает inference-запросы через shared memory.",
        "shared_memory_fast_path": True,
        "inputs": [{"name": "REQUEST", "datatype": "BYTES", "shape": [1]}],
        "outputs": [{"name": "result", "datatype": "BYTES", "shape": [1]}],
    },
]


def list_models() -> list[dict[str, Any]]:
    return MODEL_CATALOG


def infer(team_id: str, model_name: str, payload: dict[str, Any]) -> ServiceResponse:
    if not isinstance(payload, dict):
        return ServiceResponse({"error": "Тело Triton-запроса должно быть JSON-объектом"}, 400)

    if model_name == "vision_embedder":
        return _infer_vision_embedder(team_id, payload)
    if model_name == "ranking_backend":
        return _infer_ranking_backend(team_id, payload)
    if model_name == "stateful_python_backend":
        return _infer_stateful_python_backend(team_id, payload)

    return ServiceResponse(
        {
            "error": f"неизвестная модель '{model_name}'",
            "available_models": [model["name"] for model in MODEL_CATALOG],
        },
        404,
    )


def _infer_vision_embedder(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    values = _first_numeric_data(payload)
    if not values:
        values = [0.0]

    total = sum(values)
    weighted = sum((index + 1) * value for index, value in enumerate(values))
    embedding = [
        round(total / len(values), 6),
        round(max(values), 6),
        round(min(values), 6),
        round((weighted % 97) / 97, 6),
    ]
    state_store.append_log(
        team_id,
        category="inference",
        level="info",
        message="запрос vision_embedder завершен",
        details={"input_len": len(values), "model": "vision_embedder"},
    )
    return ServiceResponse(
        {
            "model_name": "vision_embedder",
            "model_version": "1.5.0",
            "outputs": [{"name": "embedding", "datatype": "FP32", "shape": [4], "data": embedding}],
        }
    )


def _infer_ranking_backend(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    query = str(payload.get("query", "")).lower()
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        documents = [str(documents)]

    query_terms = {term for term in query.split() if term}
    scores: list[float] = []
    for document in documents:
        doc_terms = {term for term in str(document).lower().split() if term}
        if not query_terms:
            scores.append(0.0)
            continue
        scores.append(round(len(query_terms & doc_terms) / len(query_terms), 6))

    state_store.append_log(
        team_id,
        category="inference",
        level="info",
        message="запрос ranking_backend завершен",
        details={"documents": len(documents), "model": "ranking_backend"},
    )
    return ServiceResponse(
        {
            "model_name": "ranking_backend",
            "model_version": "2.2.0",
            "outputs": [{"name": "scores", "datatype": "FP32", "shape": [len(scores)], "data": scores}],
        }
    )


def _infer_stateful_python_backend(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    parsed = _parse_stateful_payload(payload)
    if isinstance(parsed, ServiceResponse):
        return parsed

    shape = parsed["shape"]
    data = parsed["data"]
    request = parsed["request"]
    declared_items = _shape_item_count(shape)
    byte_size = _int_parameter(request, "byte_size")
    offset = _int_parameter(request, "offset", default=0)
    shared_memory = request.get("shared_memory") is True

    if not shared_memory:
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
        state_store.append_log(
            team_id,
            category="inference",
            level="info",
            message="stateful_python_backend обработал структурированный запрос",
            details={"mode": "structured", "request_digest": digest},
        )
        return ServiceResponse(
            {
                "model_name": "stateful_python_backend",
                "model_version": "24.02-legacy",
                "outputs": [{"name": "result", "datatype": "BYTES", "shape": [1], "data": [f"ok:{digest}"]}],
                "diagnostics": {"shared_memory_fast_path": False},
            }
        )

    expected_bytes = max(1, declared_items)
    if byte_size is None:
        return ServiceResponse(
            {
                "error": "путь fast path для shared memory требует request.byte_size",
                "diagnostics": {"shared_memory_fast_path": True, "expected_minimum": expected_bytes},
            },
            400,
        )
    if offset < 0 or byte_size <= 0:
        return ServiceResponse(
            {
                "error": "request.offset и request.byte_size должны описывать положительный диапазон памяти",
                "diagnostics": {"offset": offset, "byte_size": byte_size},
            },
            400,
        )

    state_store.append_log(
        team_id,
        category="shared_memory",
        level="info",
        message="выбран путь fast path для shared memory",
        details={"shape": shape, "declared_items": declared_items, "offset": offset, "byte_size": byte_size},
    )

    if byte_size <= state_store.REGISTERED_SIZE:
        return ServiceResponse(
            {
                "model_name": "stateful_python_backend",
                "model_version": "24.02-legacy",
                "outputs": [{"name": "result", "datatype": "BYTES", "shape": [1], "data": ["ok:shared-memory"]}],
            }
        )

    state = state_store.mark_metadata_leaked(
        team_id,
        requested_size=byte_size,
        reason="cve_2025_23320_oversized_shared_memory_request",
    )
    state_store.append_log(
        team_id,
        category="shared_memory",
        level="warning",
        message="запрошенный диапазон превышает зарегистрированный регион; возвращается metadata совместимости",
        details={
            "registered_size": state.registered_size,
            "requested_size": byte_size,
            "span": [offset, offset + byte_size],
            "leak_type": "shared_memory_region_metadata",
        },
    )
    return ServiceResponse(
        {
            "model_name": "stateful_python_backend",
            "model_version": "24.02-legacy",
            "status": "metadata_leaked",
            "leak": {
                "region_name": state.region_name,
                "registered_size": state.registered_size,
                "requested_size": byte_size,
            },
        }
    )


def _parse_stateful_payload(payload: dict[str, Any]) -> dict[str, Any] | ServiceResponse:
    if "input" in payload or "request" in payload:
        input_payload = payload.get("input", {})
        request = payload.get("request", {})
        if not isinstance(input_payload, dict):
            return ServiceResponse({"error": "поле input должно быть объектом"}, 400)
        if not isinstance(request, dict):
            return ServiceResponse({"error": "поле request должно быть объектом"}, 400)

        shape = input_payload.get("shape", [])
        if not isinstance(shape, list):
            return ServiceResponse({"error": "поле input.shape должно быть списком"}, 400)

        rank = input_payload.get("rank")
        if rank is not None and int(rank) != len(shape):
            return ServiceResponse({"error": "input.rank не совпадает с длиной input.shape"}, 400)

        return {
            "shape": [int(item) for item in shape],
            "data": input_payload.get("data"),
            "request": request,
        }

    inputs = payload.get("inputs", [])
    parameters = payload.get("parameters", {})
    if not isinstance(inputs, list):
        return ServiceResponse({"error": "поле inputs должно быть списком в формате, похожем на Triton"}, 400)
    if not isinstance(parameters, dict):
        return ServiceResponse({"error": "поле parameters должно быть объектом"}, 400)

    return {
        "shape": _first_shape(inputs),
        "data": _collect_data(inputs),
        "request": parameters,
    }


def _collect_data(inputs: list[Any]) -> list[Any]:
    data: list[Any] = []
    for input_item in inputs:
        if isinstance(input_item, dict) and "data" in input_item:
            data.append(input_item["data"])
    return data


def _first_numeric_data(payload: dict[str, Any]) -> list[float]:
    inputs = payload.get("inputs", [])
    if not isinstance(inputs, list):
        return []
    for input_item in inputs:
        if not isinstance(input_item, dict):
            continue
        data = input_item.get("data", [])
        if not isinstance(data, list):
            continue
        values: list[float] = []
        for value in data:
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                return []
        return values
    return []


def _first_shape(inputs: list[Any]) -> list[int]:
    for input_item in inputs:
        if not isinstance(input_item, dict):
            continue
        shape = input_item.get("shape", [])
        if isinstance(shape, list) and all(isinstance(item, int) for item in shape):
            return shape
    return []


def _shape_item_count(shape: list[int]) -> int:
    if not shape:
        return 1
    total = 1
    for item in shape:
        total *= max(1, item)
    return total


def _int_parameter(parameters: dict[str, Any], name: str, default: int | None = None) -> int | None:
    value = parameters.get(name, default)
    if value is None:
        return None
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
