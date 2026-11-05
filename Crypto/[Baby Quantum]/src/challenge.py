import os
import secrets
import sys
from pathlib import Path

import cirq


def message_bits(data):
    bits = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def bits_to_bytes(bits):
    if len(bits) % 8 != 0:
        raise ValueError("bit length is not a multiple of 8")
    out = bytearray()
    for offset in range(0, len(bits), 8):
        byte = 0
        for bit in bits[offset : offset + 8]:
            byte = (byte << 1) | bit
        out.append(byte)
    return bytes(out)


def one_qubit_circuit(q, ops):
    circuit = cirq.Circuit(ops)
    if q not in circuit.all_qubits():
        circuit.append(cirq.I(q))
    return circuit


def conjugate_ops(q, bit, basis):
    """Кодирование шести состояний

    Z: |0>, |1>
    X: |+>, |->
    Y: |+i>, |-i>   (H, затем S)
    Бит 0 увеличивает собственное значение +1, бит 1 уменьшает собственное значение -1.
    """
    ops = []
    if bit:
        ops.append(cirq.X(q))
    if basis == "X":
        ops.append(cirq.H(q))
    elif basis == "Y":
        ops.append(cirq.H(q))
        ops.append(cirq.S(q))
    elif basis != "Z":
        raise ValueError(f"unknown basis {basis}")
    return ops


def otp_ops(q, pad_x, pad_z):
    """Квантовый одноразовый блокнот X^{pad_x} Z^{pad_z}.
    """
    ops = []
    if pad_x:
        ops.append(cirq.X(q))
    if pad_z:
        ops.append(cirq.Z(q))
    return ops


def scrambler_ops(q, index, nonce):
    """Открытый Клиффордов слой. Nonce — IV.
    """
    a = nonce[index % len(nonce)]
    b = nonce[(index * 3 + 1) % len(nonce)]
    ops = [cirq.H(q)]
    if a & 1:
        ops.append(cirq.S(q))
    if a & 2:
        ops.append(cirq.X(q))
    if a & 4:
        ops.append(cirq.Z(q))
    if b & 1:
        ops.append(cirq.H(q))
    if b & 2:
        ops.append(cirq.S(q))
    if b & 4:
        ops.append(cirq.X(q))
    ops.append(cirq.S(q))
    return ops


def public_ops(q, pad_x, pad_z, index, nonce):
    return otp_ops(q, pad_x, pad_z) + scrambler_ops(q, index, nonce)


def encrypt_qubit(bit, basis, pad_x, pad_z, index, nonce, sim):
    q = cirq.LineQubit(0)
    ops = conjugate_ops(q, bit, basis) + public_ops(q, pad_x, pad_z, index, nonce)
    return sim.simulate(one_qubit_circuit(q, ops)).final_state_vector


def fmt_amp(amp):
    return f"{float(amp.real):.9g},{float(amp.imag):.9g}"


def render_dump(nonce, qubits):
    lines = [
        f"Nonce (hex) = {nonce.hex()}",
        f"Длина сообщения (бит) = {len(qubits)}",
        "",
        "Шифртекст:",
    ]
    for index, (state, pad_x, pad_z) in enumerate(qubits):
        lines.append(
            f"  {index}: pad_x={pad_x} pad_z={pad_z} "
            f"amp0={fmt_amp(state[0])} amp1={fmt_amp(state[1])}"
        )
    return "\n".join(lines) + "\n"


def run_protocol(message, out_path):
    bits = message_bits(message)
    nonce = secrets.token_bytes(32)
    sim = cirq.Simulator()
    qubits = []
    for index, bit in enumerate(bits):
        basis = secrets.choice(("Z", "X", "Y"))
        pad_x = secrets.randbits(1)
        pad_z = secrets.randbits(1)
        state = encrypt_qubit(bit, basis, pad_x, pad_z, index, nonce, sim)
        qubits.append((state, pad_x, pad_z))

    out_path.write_text(render_dump(nonce, qubits), encoding="utf-8")
    return len(bits)


def main():
    flag = os.environ.get("FLAG", "flag{THIS_IS_FAKE_FLAG}")
    out_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().with_name("challenge.txt")
    )
    n = run_protocol(flag.encode(), out_path)
    print(f"wrote {out_path} ({n} qubits)")

if __name__ == "__main__":
    main()
