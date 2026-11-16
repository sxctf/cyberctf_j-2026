#!/usr/bin/env python3
"""
Решение «Ворона и решетчатый сыр».

Задача — BDD в q-арной решётке: target = point + e (mod q), point ∈ L,
|e_i| <= cheese_bound. Вложение Каннана: к базису L добавляется строка
(target, M). В новой решётке есть короткий вектор (e, M); LLL его не
достаёт, прогрессивный BKZ — достаёт (обычно на блоке 30–40, 0.5–4 мин).

Запуск (нужен fpylll):
    sage -python solve.py challenge.json
    python3 solve.py challenge.json        # если fpylll установлен через pip
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time

from fpylll import BKZ, LLL, IntegerMatrix
from fpylll.algorithms.bkz2 import BKZReduction

DOMAIN = b"crow-lattice-cheese-v2"
FLAG_RE = re.compile(rb"[A-Za-z0-9_]+\{[\x20-\x7e]+\}")
BLOCK_SIZES = (10, 20, 30, 40, 50)


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


def decrypt(ct: bytes, e: list[int]) -> bytes:
    ks = keystream(derive_key(e), len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks))


def find_cheese(A: IntegerMatrix, m: int, scale: int, bound: int, ct: bytes) -> bytes | None:
    for i in range(A.nrows):
        row = [A[i, j] for j in range(m + 1)]
        if abs(row[m]) != scale:
            continue
        sign = 1 if row[m] == scale else -1
        e = [sign * v for v in row[:m]]
        if max(abs(v) for v in e) > bound:
            continue
        pt = decrypt(ct, e)
        if FLAG_RE.fullmatch(pt):
            print(f"[+] row {i}: |e| ~ {sum(v * v for v in e) ** 0.5:.2f}", flush=True)
            return pt
    return None


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "challenge.json"
    with open(path, encoding="utf-8") as fh:
        pub = json.load(fh)

    m = pub["m"]
    bound = pub["cheese_bound"]
    basis = pub["basis"]
    target = pub["target"]
    ct = bytes.fromhex(pub["ciphertext"])

    scale = bound
    rows = [row + [0] for row in basis] + [target + [scale]]
    A = IntegerMatrix.from_matrix(rows)

    t0 = time.time()
    print(f"[*] LLL on {A.nrows}x{A.ncols} ...", flush=True)
    LLL.reduction(A)
    print(f"[*] LLL done in {time.time() - t0:.1f}s", flush=True)
    flag = find_cheese(A, m, scale, bound, ct)

    if flag is None:
        bkz = BKZReduction(A)
        for block in BLOCK_SIZES:
            t0 = time.time()
            print(f"[*] BKZ-{block} ...", flush=True)
            params = BKZ.Param(
                block_size=block,
                max_loops=8,
                flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT | BKZ.GH_BND,
            )
            bkz(params)
            print(f"[*] BKZ-{block} done in {time.time() - t0:.1f}s", flush=True)
            flag = find_cheese(A, m, scale, bound, ct)
            if flag is not None:
                break

    if flag is None:
        print("[-] short vector not found", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Flag: {flag.decode()}")


if __name__ == "__main__":
    main()
