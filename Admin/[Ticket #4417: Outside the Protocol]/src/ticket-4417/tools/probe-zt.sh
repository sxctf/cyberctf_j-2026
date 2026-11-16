#!/usr/bin/env bash
# tools/probe-zt.sh
# Использование:
#   tools/probe-zt.sh                            # все базовые проверки
#   tools/probe-zt.sh kotslon@zt.zt              # + проверка specific user
set -u

IP="${ZT_IP:-10.63.0.40}"
HOST="${ZT_HOST:-zerotrace.jeopardy.ctflab.local}"
EMAIL="${1:-}"

RESOLVE=(--resolve "${HOST}:443:${IP}")

echo "=== root ==="
curl -ks "${RESOLVE[@]}" -o /tmp/body -w "%{http_code} %{content_type}\n" "https://${HOST}/"
head -c 300 /tmp/body; echo; echo

echo "=== login candidates ==="
for p in /auth/login /api/auth/login /api/v1/auth/login /login /api/login /v1/auth/login /signin /api/signin; do
  code=$(curl -ks "${RESOLVE[@]}" -o /tmp/body -w "%{http_code}" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"email":"x","password":"y"}' \
    "https://${HOST}${p}")
  echo "  $p → $code"
  if [ "$code" != "404" ] && [ "$code" != "000" ]; then
    echo "    body: $(head -c 200 /tmp/body)"
  fi
done
echo

echo "=== public endpoints ==="
for p in /users /users/me /admin/users; do
  code=$(curl -ks "${RESOLVE[@]}" -o /tmp/body -w "%{http_code}" "https://${HOST}${p}")
  echo "  GET $p → $code"
  if [ "$code" != "404" ]; then
    echo "    body: $(head -c 200 /tmp/body)"
  fi
done

if [ -n "${EMAIL}" ]; then
  echo
  echo "=== resolve ${EMAIL} ==="
  echo "  вписывай рабочие пути/поля в config.env после того, как увидишь 200 на login"
fi