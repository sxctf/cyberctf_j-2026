#!/bin/sh
# роль выбирается первым аргументом (CMD в Dockerfile / command в compose)
set -e

case "${1:-sim}" in
    gateway) exec python3 -m app.gateway run ;;
    auth)    exec python3 -m app.auth ;;
    verify)  exec python3 -m app.verify ;;
    sim)     exec python3 -m app.sim ;;
    *)
        echo "unknown role: $1" >&2
        exit 1
        ;;
esac