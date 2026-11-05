"""Оценка ресурсов с учетом отказоустойчивости для VaultKDF."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from challenge.circuit import DATA_BITS, TOTAL_QUBITS, GateOp

MAX_QUBITS = 12
MAX_T_COUNT = 4
MAX_DEPTH = 48
MAX_OPERATIONS = 64


@dataclass(frozen=True, slots=True)
class ResourceReport:
    qubits: int
    t_count: int
    depth: int
    operations: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    def within_budget(self) -> bool:
        return (
            self.qubits <= MAX_QUBITS
            and self.t_count <= MAX_T_COUNT
            and self.depth <= MAX_DEPTH
            and self.operations <= MAX_OPERATIONS
        )


def _primitive_depth(operations: Iterable[GateOp], qubits: int) -> int:
    layers = [0] * qubits
    for operation in operations:
        if operation.gate in {"add", "sub"}:
            layer = max(layers[:DATA_BITS]) + 6 * DATA_BITS
            for index in range(DATA_BITS):
                layers[index] = layer
            continue
        if operation.gate == "ccx":
            duration = 8
        else:
            duration = 1
        layer = max((layers[index] for index in operation.qubits), default=0) + duration
        for index in operation.qubits:
            layers[index] = layer
    return max(layers, default=0)


def estimate_resources(
    operations: Iterable[GateOp],
    *,
    qubits: int = TOTAL_QUBITS,
) -> ResourceReport:
    operations = tuple(operations)
    t_count = 0
    requires_carry_register = False
    for operation in operations:
        if operation.gate in {"t", "tdg"}:
            t_count += 1
        elif operation.gate == "ccx":
            t_count += 7
        elif operation.gate in {"add", "sub"}:
            t_count += 7 * (2 * DATA_BITS - 1)
            requires_carry_register = True
    logical_qubits = qubits + (DATA_BITS - 1 if requires_carry_register else 0)
    return ResourceReport(
        qubits=logical_qubits,
        t_count=t_count,
        depth=_primitive_depth(operations, qubits),
        operations=len(operations),
    )


def budget() -> dict[str, int]:
    return {
        "qubits": MAX_QUBITS,
        "t_count": MAX_T_COUNT,
        "depth": MAX_DEPTH,
        "operations": MAX_OPERATIONS,
    }
