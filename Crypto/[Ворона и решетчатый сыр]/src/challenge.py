#!/usr/bin/env python3
"""
    Вороне где-то бог послал кусочек сыру;
    На ель Ворона взгромоздясь,
    Позавтракать было совсем уж собралась...

Сыр решётчатый: дырки в нём стоят по узлам решётки L в Z^M. Ворона
клюнула рядом с одной из дырок (скрытая точка решётки), промахнувшись
на малый вектор e. Лисица видит след клюва (вектор t) и знает рецепт
сыра — но лишь в скособоченных координатах (публичный базис). Ключ от
флага — точное положение следа относительно дырки, вектор e.

Запуск:
    FLAG='flag{...}' python3 challenge.py [challenge.json]
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sys

M = 160              # размерность решётки (длина векторов)
N = 80               # ранг «свободной» части: сколько координат выбирает Ворона
Q = 4093             # модуль: дырки повторяются с периодом Q по каждой оси
CHEESE_BOUND = 5     # |e_i| <= CHEESE_BOUND, сдвиг следа клюва от дырки
DOMAIN = b"crow-lattice-cheese-v2"

rng = secrets.SystemRandom()


def public_basis(a_prime: list[list[int]]) -> list[list[int]]:
    """Базис решётки L = { x·[I_N | A'] mod Q } в виде строк m x m."""
    rows: list[list[int]] = []
    for i in range(N):
        rows.append([1 if j == i else 0 for j in range(N)] + a_prime[i])
    for i in range(M - N):
        rows.append([0] * N + [Q if j == i else 0 for j in range(M - N)])
    return rows


def lattice_point(x: list[int], a_prime: list[list[int]]) -> list[int]:
    tail = [sum(x[i] * a_prime[i][j] for i in range(N)) % Q for j in range(M - N)]
    return [v % Q for v in x] + tail


def derive_key(e: list[int]) -> bytes:
    material = DOMAIN + b"|" + " ".join(str(v) for v in e).encode()
    return hashlib.sha256(material).digest()


def keystream(key: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def encrypt_flag(flag: bytes, e: list[int]) -> bytes:
    ks = keystream(derive_key(e), len(flag))
    return bytes(a ^ b for a, b in zip(flag, ks))


def norm(v: list[int]) -> float:
    return math.sqrt(sum(x * x for x in v))


def gaussian_heuristic() -> float:
    det_root = Q ** ((M - N) / M)
    return math.sqrt(M / (2 * math.pi * math.e)) * det_root


def main() -> None:
    flag = os.getenv("FLAG", "flag{THIS_IS_FAKE_FLAG}").encode()
    out_path = sys.argv[1] if len(sys.argv) > 1 else "challenge.json"

    a_prime = [[rng.randrange(Q) for _ in range(M - N)] for _ in range(N)]
    basis = public_basis(a_prime)                       

    hole = [rng.randrange(Q) for _ in range(N)]        
    cheese = [rng.randint(-CHEESE_BOUND, CHEESE_BOUND) for _ in range(M)] 
    point = lattice_point(hole, a_prime)
    target = [(p + c) % Q for p, c in zip(point, cheese)]

    gh = gaussian_heuristic()
    assert norm(cheese) < gh / 2, "слишком далеко"

    public = {
        "m": M,
        "n": N,
        "q": Q,
        "cheese_bound": CHEESE_BOUND,
        "basis": basis,
        "target": target,
        "ciphertext": encrypt_flag(flag, cheese).hex(),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(public, fh)

    print(f"[+] wrote {out_path}", file=sys.stderr)
    print(f"[+] |e| = {norm(cheese):.2f}, lambda_1 ~ {gh:.2f} (GH), gap ~ {gh / norm(cheese):.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
