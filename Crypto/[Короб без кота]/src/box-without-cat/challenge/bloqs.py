"""Неоптимальная реализация VaultKDF в формате Qualtran"""

from __future__ import annotations

from functools import cached_property

import attrs
from qualtran import Bloq, BloqBuilder, Signature

from challenge.circuit import TOTAL_QUBITS, GateOp, naive_program


@attrs.frozen
class InstructionBloq(Bloq):
    """Листовой блок, использующий одну обратимую инструкцию VaultKDF"""

    operation: GateOp

    @cached_property
    def signature(self) -> Signature:
        return Signature.build(q=TOTAL_QUBITS)

    def __str__(self) -> str:
        return self.operation.label()


@attrs.frozen
class VaultKDF(Bloq):
    """Публичный составной блок, который нужно оптимизировать"""

    @cached_property
    def signature(self) -> Signature:
        return Signature.build(q=TOTAL_QUBITS)

    def build_composite_bloq(self, bb: BloqBuilder, q):
        for operation in naive_program():
            q = bb.add(InstructionBloq(operation), q=q)
        return {"q": q}
