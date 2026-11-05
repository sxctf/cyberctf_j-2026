#!/bin/bash
set -euo pipefail

python3 server.py &
SRV=$!

sleep 0.5

python3 web/webserver.py &
WEB=$!

term() { kill "$SRV" "$WEB" 2>/dev/null || true; }
trap term TERM INT

wait -n
term
exit 1
