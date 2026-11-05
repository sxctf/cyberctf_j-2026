from __future__ import annotations

__all__ = ["VaultKDF", "naive_program"]


def __getattr__(name: str):
    if name == "VaultKDF":
        from challenge.bloqs import VaultKDF

        return VaultKDF
    if name == "naive_program":
        from challenge.circuit import naive_program

        return naive_program
    raise AttributeError(name)
