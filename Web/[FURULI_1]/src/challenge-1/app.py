"""
CTF Challenge 1: "The Archive of the Old Observatory"
Vulnerability: LFI / RFI (A03:2021 - Injection)

Legend: an old observatory exposes its archive portal. Users can view
static help pages and load language packs from the official CDN.
Hidden flaw: the page/language parameters are passed to a template loader
without validation -> Local File Inclusion, and remote URLs are trusted
-> Remote File Inclusion.

Flag: FLAG{lfi_0bs3rv4t0ry_ch4rt3d_c0m3t_7f9x}
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone

from flask import Flask, request, render_template_string, abort, g

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# The flag is baked into the application code. It is also copied into
# /opt/secrets/flag.txt inside the container so that LFI can reach it.
# ---------------------------------------------------------------------------
SECRET_FLAG = "FLAG{lfi_0bs3rv4t0ry_ch4rt3d_c0m3t_7f9x}"

LOG_DB = os.environ.get("LOG_DB", "/data/userlog.db")

app = Flask(__name__)
app.config["SECRET_FLAG"] = SECRET_FLAG


def db():
    if "db" not in g:
        g.db = sqlite3.connect(LOG_DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def init_log_db():
    os.makedirs(os.path.dirname(LOG_DB), exist_ok=True)
    conn = sqlite3.connect(LOG_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ip TEXT,
            method TEXT,
            path TEXT,
            query TEXT,
            user_agent TEXT,
            action TEXT,
            detail TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def log_action(action, detail=""):
    """Log every user action into the separate SQLite DB mounted via volume."""
    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(
            "INSERT INTO user_actions (ts, ip, method, path, query, user_agent,"
            " action, detail) VALUES (?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                request.headers.get("X-Forwarded-For", request.remote_addr),
                request.method,
                request.path,
                request.query_string.decode(errors="replace"),
                request.headers.get("User-Agent", ""),
                action,
                detail,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # never break the challenge because of logging
        logging.getLogger("ctf").warning("log failed: %s", e)


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{{ title }}</title>
<style>
 body{font-family:Georgia,serif;background:#0d1117;color:#c9d1d9;margin:40px}
 a{color:#58a6ff} .box{border:1px solid #30363d;padding:20px;border-radius:8px;
 background:#161b22;white-space:pre-wrap}
</style></head>
<body>
<h1>&#128301; {{ title }}</h1>
<p><a href="/">Home</a> | <a href="/page?file=about.html">About</a> |
<a href="/page?file=help.html">Help</a> | <a href="/lang">Language pack</a></p>
<div class="box">{{ content }}</div>
</body></html>
"""

PAGES_DIR = os.path.join(APP_DIR, "pages")


@app.before_request
def log_every_request():
    log_action("request", f"{request.method} {request.full_path}")


@app.route("/")
def index():
    content = (
        "Welcome to the Old Observatory Archive Portal.\n\n"
        "This terminal keeps the star charts safe since 1899.\n"
        "Browse the documentation with the links above."
    )
    log_action("index", "home page viewed")
    return render_template_string(PAGE_TEMPLATE,
                                  title="Old Observatory Archive",
                                  content=content)


@app.route("/page")
def page():
    """Vulnerable endpoint: LOCAL FILE INCLUSION.

    The 'file' parameter is joined to PAGES_DIR without any sanitisation,
    so '../' sequences let the player read arbitrary files on disk
    (e.g. ../../opt/secrets/flag.txt or /proc/self/environ).
    """
    name = request.args.get("file", "home.txt")
    target = os.path.join(PAGES_DIR, name)          # <-- no traversal check!
    log_action("page_view", f"requested file={name!r} resolved={target!r}")
    try:
        with open(target, "r", errors="replace") as fh:
            content = fh.read()
    except Exception as e:
        log_action("page_error", f"file={name!r} error={e}")
        content = f"[archive clerk] cannot fetch '{name}': {e}"
    return render_template_string(PAGE_TEMPLATE,
                                  title=f"Archive page: {name}",
                                  content=content)


@app.route("/lang")
@app.route("/lang/<path:pack>")
def lang(pack=None):
    """Vulnerable endpoint: REMOTE FILE INCLUSION.

    If ?src= is a URL the server fetches it and renders the response body
    as a template — classic RFI. The legacy static packs use /lang/<pack>.
    """
    src = request.args.get("src")
    if src:
        import urllib.request
        log_action("rfi_fetch", f"src={src!r}")
        try:
            with urllib.request.urlopen(src, timeout=5) as resp:
                remote = resp.read().decode(errors="replace")
        except Exception as e:
            log_action("rfi_error", f"src={src!r} error={e}")
            remote = f"[language daemon] failed to load pack from {src}: {e}"
        # VULNERABLE: the remotely fetched pack text is rendered as a
        # template expression -> SSTI via RFI chain. A payload such as
        #   {{ config["SECRET_FLAG"] }}
        # or
        #   {{ ''.__class__.__mro__[1].__subclasses__() }}
        # is evaluated server-side.
        from jinja2 import Template
        try:
            # The remote pack is rendered with the app's Jinja environment,
            # so {{ config[...] }}, {{ request... }} etc. all resolve.
            rendered = app.jinja_env.from_string(remote).render()
        except Exception as e:
            log_action("rfi_ssti_error", f"src={src!r} error={e}")
            rendered = f"[language daemon] pack parse error: {e}"
        return render_template_string(PAGE_TEMPLATE,
                                      title=f"Language pack ({src})",
                                      content=rendered)
    pack_name = pack or "en.txt"
    target = os.path.join(APP_DIR, "langs", pack_name)
    log_action("lang_view", f"pack={pack_name!r}")
    try:
        with open(target, errors="replace") as fh:
            content = fh.read()
    except Exception as e:
        content = f"[language daemon] unknown pack '{pack_name}': {e}"
    return render_template_string(PAGE_TEMPLATE,
                                  title=f"Language pack: {pack_name}",
                                  content=content)


@app.route("/health")
def health():
    return {"status": "ok", "service": "challenge-lfi"}


init_log_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
