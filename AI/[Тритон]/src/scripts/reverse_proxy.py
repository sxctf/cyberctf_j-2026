#!/usr/bin/env python3
from __future__ import annotations

from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from urllib.parse import urlparse


UPSTREAM = urlparse(os.getenv("UPSTREAM_BASE_URL", "http://triton-challenge:8000"))
PORT = int(os.getenv("GATEWAY_PORT", "8000"))
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class FixedUpstreamProxy(BaseHTTPRequestHandler):
    server_version = "TritonChallengeGateway/1.0"

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        headers["Host"] = UPSTREAM.netloc

        try:
            connection = HTTPConnection(UPSTREAM.hostname, UPSTREAM.port or 8000, timeout=10)
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream_response = connection.getresponse()
            response_body = upstream_response.read()
        except OSError:
            self.send_error(HTTPStatus.BAD_GATEWAY, "upstream unavailable")
            return

        self.send_response(upstream_response.status, upstream_response.reason)
        for key, value in upstream_response.getheaders():
            if key.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response_body)

    def log_message(self, format: str, *args) -> None:
        print("%s - %s" % (self.address_string(), format % args), flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), FixedUpstreamProxy)
    print(f"gateway listening on 0.0.0.0:{PORT}, upstream={UPSTREAM.geturl()}", flush=True)
    server.serve_forever()
