"""
CTF Challenge 2: "Supply Depot of the Observatory"
Vulnerability: Path Traversal (A01:2021 - Broken Access Control)

Legend: the same Old Observatory network now runs a supply depot where
astronomers download equipment manuals and inventory sheets from the
shared warehouse folder. The download endpoint builds filesystem paths
from the user-supplied ?file= parameter without normalisation, allowing
directory traversal ("../") to read files outside the public folder -
including the vault file that holds the flag.

Flag: FLAG{p4th_tr4vers4l_d3p0t_v4ult_51z3_42}
"""

import os
import re
import sqlite3
import logging
from datetime import datetime, timezone

from flask import Flask, request, send_file, abort, render_template_string, g

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(APP_DIR, "warehouse", "public")
VAULT_DIR = os.path.join(APP_DIR, "warehouse", "vault")   # outside public reach

SECRET_FLAG = "FLAG{p4th_tr4vers4l_d3p0t_v4ult_51z3_42}"
LOG_DB = os.environ.get("LOG_DB", "/data/userlog.db")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Action logging into a separate SQLite DB (mounted through a docker volume)
# ---------------------------------------------------------------------------
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
    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(
            "INSERT INTO user_actions (ts, ip, method, path, query,"
            " user_agent, action, detail) VALUES (?,?,?,?,?,?,?,?)",
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
    except Exception as e:
        logging.getLogger("ctf").warning("log failed: %s", e)


INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{{ title }}</title>
<style>
 body{font-family:'Courier New',monospace;background:#101510;color:#b6f0b6;margin:40px}
 a{color:#79c0ff} table{border-collapse:collapse} td,th{padding:6px 14px;
 border:1px solid #2c3a2c}
</style></head>
<body>
<h1>&#128230; {{ title }}</h1>
<p>Old Observatory Supply Depot &mdash; shared warehouse terminal.</p>
<p>Available documents (click to download):</p>
<table><tr><th>File</th><th>Description</th></tr>
{% for name, desc in files %}
<tr><td><a href="/download?file={{ name }}">{{ name }}</a></td><td>{{ desc }}</td></tr>
{% endfor %}
</table>
<p style="margin-top:2em;color:#666">
Depot note: internal paperwork lives in ../vault (staff only, obviously).
</p>
</body></html>
"""


@app.before_request
def log_every_request():
    log_action("request", f"{request.method} {request.full_path}")


@app.route("/")
def index():
    files = []
    if os.path.isdir(PUBLIC_DIR):
        for f in sorted(os.listdir(PUBLIC_DIR)):
            files.append((f, "depot document"))
    log_action("index", "catalogue listed")
    return render_template_string(INDEX_TEMPLATE,
                                  title="Observatory Supply Depot",
                                  files=files)


@app.route("/download")
def download():
    """VULNERABLE: PATH TRAVERSAL (A01 - Broken Access Control).

    Builds an absolute path with os.path.join(PUBLIC_DIR, user_input).
    A '../' sequence escapes PUBLIC_DIR; there is no containment check.
    """
    name = request.args.get("file", "")
    if not name:
        log_action("download_error", "missing file parameter")
        abort(400, "missing ?file=")

    target = os.path.join(PUBLIC_DIR, name)      # <-- traversal possible here
    log_action("download_try", f"file={name!r} resolved={target!r}")

    if not os.path.isfile(target):
        log_action("download_miss", f"file={name!r} not found")
        abort(404, "no such document in the depot")

    log_action("download_ok", f"served file={target!r}")
    return send_file(target, as_attachment=True, download_name=os.path.basename(target))


@app.route("/flag-check", methods=["POST"])
def flag_check():
    """Optional verification endpoint: paste the flag you captured."""
    submitted = (request.form.get("flag") or
                 (request.get_json(silent=True) or {}).get("flag", ""))
    ok = bool(re.fullmatch(r"\s*" + re.escape(SECRET_FLAG) + r"\s*", submitted))
    log_action("flag_check", f"correct={ok} submitted={submitted[:60]!r}")
    return {"correct": ok,
            "message": "Correct! Flag captured." if ok else "Wrong flag."}


@app.route("/health")
def health():
    return {"status": "ok", "service": "challenge-traversal"}


init_log_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
