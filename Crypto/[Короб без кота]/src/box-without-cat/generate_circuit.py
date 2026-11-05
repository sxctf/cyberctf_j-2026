"""Пример генерации неоптимальной схемы VaultKDF в circuit.json."""

from __future__ import annotations

import json
from pathlib import Path

from challenge.circuit import TOTAL_QUBITS, GateOp, naive_program


def operation_payload(operation: GateOp) -> dict[str, object]:
    payload: dict[str, object] = {"gate": operation.gate}
    if operation.qubits:
        payload["qubits"] = list(operation.qubits)
    if operation.value is not None:
        payload["value"] = operation.value
    return payload


def build() -> dict[str, object]:
    return {
        "n_qubits": TOTAL_QUBITS,
        "operations": [operation_payload(operation) for operation in naive_program()],
    }


def main() -> None:
    path = Path("circuit.json")
    path.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
