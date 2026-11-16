import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.common.config import load_config


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


class ResolveHandler(BaseHTTPRequestHandler):
    users = {}
    teams = {}

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/resolve":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            self._send(400, {"valid": False, "error": "bad json"})
            return

        email = (body.get("email") or "").strip().lower()
        if not email:
            self._send(200, {"valid": False, "error": "empty email"})
            return

        user = self.users.get(email)
        if not user:
            self._send(200, {"valid": False, "error": "user not found"})
            return

        team_id = user.get("team_id")
        if team_id in (None, "", 0):
            self._send(200, {"valid": False, "error": "user has no team"})
            return

        team = self.teams.get(team_id)
        if not team:
            self._send(200, {"valid": False, "error": "team not found"})
            return

        self._send(200, {
            "valid": True,
            "user_id": user.get("id"),
            "team_id": team_id,
            "team_name": team.get("name", ""),
        })


def main():
    cfg = load_config()
    users_list = load_json(cfg.USERS_FILE, [])
    teams_list = load_json(cfg.TEAMS_FILE, [])
    ResolveHandler.users = {u["email"].strip().lower(): u for u in users_list if "email" in u}
    ResolveHandler.teams = {t["id"]: t for t in teams_list if "id" in t}

    host, port = cfg.AUTH_ADDR.split(":")
    srv = ThreadingHTTPServer((host, int(port)), ResolveHandler)
    print(f"auth on {cfg.AUTH_ADDR} users={len(ResolveHandler.users)} teams={len(ResolveHandler.teams)}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()