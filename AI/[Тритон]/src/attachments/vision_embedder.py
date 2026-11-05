# ============================================================================
# Extracted model handler: vision_embedder.
# Provided for read-only source review in CTF. Not compiled by the service.
# This model uses structured tensor input and a bounded CPU-only code path.
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class Tensor:
    name: str
    datatype: str
    shape: list[int]
    data: list[float]


def infer(request: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    tensor = _require_tensor(request, name="pixels", datatype="FP32")
    pixels = _normalize(tensor.data)

    if parameters.get("normalize", True):
        pixels = _l2_normalize(pixels)

    embedding = _project_to_four_dims(pixels)
    return {
        "model_name": "vision_embedder",
        "outputs": [
            {
                "name": "embedding",
                "datatype": "FP32",
                "shape": [4],
                "data": embedding,
            }
        ],
    }


def _require_tensor(request: dict[str, Any], name: str, datatype: str) -> Tensor:
    inputs = request.get("inputs", [])
    if not isinstance(inputs, list):
        raise ValueError("inputs must be a list")

    for item in inputs:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        if item.get("datatype") != datatype:
            raise ValueError(f"{name} must use {datatype}")

        raw_data = item.get("data", [])
        if not isinstance(raw_data, list):
            raise ValueError(f"{name}.data must be a list")

        shape = item.get("shape", [len(raw_data)])
        return Tensor(
            name=name,
            datatype=datatype,
            shape=[int(dim) for dim in shape],
            data=[float(value) for value in raw_data],
        )

    raise ValueError(f"missing tensor {name}")


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return [0.0]
    clipped = [max(0.0, min(255.0, value)) for value in values]
    return [value / 255.0 for value in clipped]


def _l2_normalize(values: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return values
    return [value / norm for value in values]


def _project_to_four_dims(values: list[float]) -> list[float]:
    buckets = [0.0, 0.0, 0.0, 0.0]
    for index, value in enumerate(values):
        buckets[index % 4] += value
    scale = max(1, len(values))
    return [round(value / scale, 6) for value in buckets]
