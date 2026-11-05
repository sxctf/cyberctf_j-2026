"""DNS logger — captures all DNS queries from sandbox container.

Runs two servers:
1. DNS server on UDP/53 — answers everything with NXDOMAIN, logs the query
2. HTTP API on 8053 — provides query log to web service

CVE-2025-46417 demonstrates DNS exfiltration via ssl.get_server_certificate + linecache.
This logger captures those queries.
"""
import asyncio
import json
import logging
import socket
import threading
import time
from collections import deque
from datetime import datetime, UTC

import os

import uvicorn
from dnslib import DNSRecord, QTYPE, RR, A, RCODE
from dnslib.server import DNSServer, BaseResolver, DNSLogger as DnsLibLogger
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Shared log (thread-safe deque)
DNS_LOG: deque[dict] = deque(maxlen=1000)
LOG_LOCK = threading.Lock()


class LoggingResolver(BaseResolver):
    """Answers all queries with NXDOMAIN and logs them."""

    def resolve(self, request, handler):
        qname = str(request.q.qname).rstrip(".")
        qtype = QTYPE[request.q.qtype]
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "unknown"

        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "qname": qname,
            "qtype": qtype,
            "client": client_ip,
        }
        with LOG_LOCK:
            DNS_LOG.appendleft(entry)

        logging.info(f"[DNS] {client_ip} -> {qtype} {qname}")

        reply = request.reply()
        reply.header.rcode = RCODE.NXDOMAIN
        return reply


# ---- HTTP API ----
api = FastAPI(title="DNS Logger API", docs_url=None)


@api.get("/queries")
def get_queries(since_ts: str = "", limit: int = 100):
    """Return recent DNS queries, optionally filtered by timestamp."""
    with LOG_LOCK:
        entries = list(DNS_LOG)

    if since_ts:
        entries = [e for e in entries if e["ts"] > since_ts]

    return entries[:limit]


@api.get("/queries/stream")
async def stream_queries():
    """SSE stream of new DNS queries."""
    from fastapi.responses import StreamingResponse

    async def generator():
        last_ts = ""
        while True:
            with LOG_LOCK:
                new_entries = [e for e in DNS_LOG if e["ts"] > last_ts]
            if new_entries:
                last_ts = new_entries[0]["ts"]
                for e in reversed(new_entries):
                    yield f"data: {json.dumps(e)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(generator(), media_type="text/event-stream")


@api.get("/health")
def health():
    return {"status": "ok", "log_size": len(DNS_LOG)}


def start_dns_server():
    resolver = LoggingResolver()
    # Suppress dnslib's own logging
    null_logger = DnsLibLogger(prefix=False)
    port = int(os.environ.get("DNS_UDP_PORT", "53"))
    server = DNSServer(resolver, port=port, address="0.0.0.0", logger=null_logger)
    server.start_thread()
    logging.info(f"DNS server started on UDP/{port}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    start_dns_server()
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("DNS_HTTP_PORT", "8053")), log_level="warning")
