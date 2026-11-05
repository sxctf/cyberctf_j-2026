"""Вывод публичного разложения и оценки ресурсов."""

from __future__ import annotations

import json

from challenge.bloqs import VaultKDF
from challenge.circuit import naive_program
from challenge.resources import budget, estimate_resources


def main() -> None:
    composite = VaultKDF().decompose_bloq()
    operations = naive_program()
    print(f"Qualtran composite instances: {len(composite.bloq_instances)}")
    print(json.dumps({"resources": estimate_resources(operations).as_dict(), "budget": budget()}, indent=2))
    for index, operation in enumerate(operations):
        print(f"{index:03d}: {operation.label()}")


if __name__ == "__main__":
    main()
