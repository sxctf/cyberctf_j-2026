from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DATA_BITS = 10
TOTAL_QUBITS = 12
MODULUS = 1 << DATA_BITS

PUBLIC_GATES = frozenset({"x", "cx", "t", "tdg", "ccx", "add", "sub"})
SUBMISSION_GATES = frozenset({"x", "cx", "t", "tdg"})


@dataclass(frozen=True, slots=True)
class GateOp:
    gate: str
    qubits: tuple[int, ...] = ()
    value: int | None = None

    def __post_init__(self) -> None:
        if self.gate not in PUBLIC_GATES:
            raise ValueError(f"unsupported gate: {self.gate}")

    def label(self) -> str:
        if self.gate in {"add", "sub"}:
            return f"{self.gate.upper()}({self.value})"
        return f"{self.gate.upper()}({','.join(map(str, self.qubits))})"


def parity_gadget(mask: Iterable[int], coefficient: int) -> list[GateOp]:
    bits = tuple(mask)
    if len(bits) < 1:
        raise ValueError("a parity gadget needs at least one qubit")
    pivot, controls = bits[-1], bits[:-1]
    operations = [GateOp("cx", (control, pivot)) for control in controls]
    phase_gate = "t" if coefficient > 0 else "tdg"
    operations.extend(GateOp(phase_gate, (pivot,)) for _ in range(abs(coefficient)))
    operations.extend(GateOp("cx", (control, pivot)) for control in reversed(controls))
    return operations


def _noisy_phase_oracle() -> list[GateOp]:
    terms = [
        ((0, 1, 4), (1, 1, -1)),
        ((2, 5), (1, 1, 1, 1, 1, 1, 1, 1)),
        ((3, 6, 9), (-1, -1, 1)),
        ((1, 7), (1, 1, -1)),
        ((0, 8, 9), (-1, -1, 1)),
    ]
    operations: list[GateOp] = []
    for mask, coefficients in terms:
        for coefficient in coefficients:
            operations.extend(parity_gadget(mask, coefficient))
    return operations


def naive_program() -> tuple[GateOp, ...]:
    operations = [
        GateOp("ccx", (0, 1, 10)),
        GateOp("ccx", (2, 3, 11)),
        GateOp("cx", (4, 5)),
        GateOp("ccx", (2, 3, 11)),
        GateOp("ccx", (0, 1, 10)),

        GateOp("add", value=173),
        GateOp("add", value=911),
        GateOp("sub", value=337),
        GateOp("add", value=641),
        GateOp("sub", value=876),

        GateOp("ccx", (0, 1, 10)),
        GateOp("cx", (4, 7)),
        GateOp("ccx", (0, 1, 10)),
        GateOp("ccx", (2, 3, 11)),
        GateOp("cx", (5, 8)),
        GateOp("ccx", (2, 3, 11)),
        GateOp("cx", (0, 3)),
        GateOp("cx", (3, 6)),
        GateOp("cx", (1, 8)),
        GateOp("x", (2,)),
    ]
    operations.extend(_noisy_phase_oracle())
    return tuple(operations)
