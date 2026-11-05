#!/usr/bin/env python3
"""Ассемблер RWVM v1 для плагинов RustWallet.

Формат: одна инструкция в строке, `;` — комментарий, `label:` — метка.
  PUSH <int>     — положить i64
  LOAD           — pop idx → push cell[idx]
  DLEN           — push число ячеек данных
  ADD SUB OUT OUTB DUP POP SWAP HALT
  JMP <label>    JZ <label>

Использование:
  rwvm.py prog.rwa            # → base64 (для UPLOAD)
  rwvm.py prog.rwa -raw > p   # → сырые байты
"""
import sys, base64, struct

OPS = {
    "HALT": (0x00, 0), "PUSH": (0x01, 8), "LOAD": (0x02, 0), "DLEN": (0x03, 0),
    "ADD": (0x04, 0), "SUB": (0x05, 0), "OUT": (0x06, 0), "OUTB": (0x07, 0),
    "DUP": (0x08, 0), "POP": (0x09, 0), "JMP": (0x0A, 2), "JZ": (0x0B, 2),
    "SWAP": (0x0C, 0),
}


def assemble(text):
                                             
    items = []
    labels = {}
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if line.endswith(":"):
            labels[line[:-1].strip()] = None                
            items.append(("LABEL", line[:-1].strip()))
            continue
        parts = line.split()
        op = parts[0].upper()
        if op not in OPS:
            raise SystemExit(f"неизвестный опкод: {op}")
        arg = parts[1] if len(parts) > 1 else None
        items.append((op, arg))

                                             
    off = 0
    for op, arg in items:
        if op == "LABEL":
            labels[arg] = off
            continue
        _, sz = OPS[op]
        off += 1 + sz

                       
    out = bytearray()
    for op, arg in items:
        if op == "LABEL":
            continue
        code, sz = OPS[op]
        out.append(code)
        if op == "PUSH":
            out += struct.pack("<q", int(arg, 0))
        elif op in ("JMP", "JZ"):
            target = labels.get(arg)
            if target is None:
                raise SystemExit(f"неизвестная метка: {arg}")
            out += struct.pack("<H", target)
        elif sz:
            raise SystemExit(f"{op} требует операнд")
    return bytes(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    raw = "-raw" in sys.argv
    if len(args) != 1:
        raise SystemExit("usage: rwvm.py <prog.rwa> [-raw]")
    code = assemble(open(args[0]).read())
    if raw:
        sys.stdout.buffer.write(code)
    else:
        print(base64.b64encode(code).decode())


if __name__ == "__main__":
    main()
