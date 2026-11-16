import http.cookiejar
import json
import ssl
import threading
import urllib.error
import urllib.request
import zlib

_lock = threading.Lock()
_login_lock = threading.Lock()
_opener = None
_admin_id = None
_admin_users_available = None


def _init(cfg):
    global _opener
    with _lock:
        if _opener is not None:
            return
        jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(jar)]
        if cfg.ZT_INSECURE:
            handlers.append(urllib.request.HTTPSHandler(
                context=ssl._create_unverified_context()))
        _opener = urllib.request.build_opener(*handlers)


def _req(cfg, method, path, body=None, timeout=None):
    _init(cfg)
    url = cfg.ZT_BASE_URL.rstrip("/") + path
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if getattr(cfg, "ZT_HOST", ""):
        headers["Host"] = cfg.ZT_HOST
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _opener.open(req, timeout=timeout or cfg.HTTP_TIMEOUT) as r:
            raw = r.read().decode(errors="replace") or "{}"
            return r.status, _safe_json(raw), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace") or "{}"
        return e.code, _safe_json(raw), raw
    except Exception as e:
        return 0, {}, f"request error: {e}"


def _safe_json(s):
    try:
        return json.loads(s)
    except Exception:
        return {}


# ============================================================
# Admin session
# ============================================================

def _ensure_admin(cfg, force=False):
    global _admin_id
    with _login_lock:
        if _admin_id is not None and not force:
            return _admin_id

        if not cfg.ZT_ADMIN_EMAIL or not cfg.ZT_ADMIN_PASSWORD:
            raise RuntimeError("ZT_ADMIN_EMAIL / ZT_ADMIN_PASSWORD не заданы")

        body = {
            cfg.ZT_LOGIN_EMAIL_FIELD: cfg.ZT_ADMIN_EMAIL,
            cfg.ZT_LOGIN_PASSWORD_FIELD: cfg.ZT_ADMIN_PASSWORD,
        }
        code, resp, raw = _req(cfg, "POST", cfg.ZT_LOGIN_PATH, body=body)

        if code in (400, 401):
            raise RuntimeError(f"admin credentials rejected: {raw[:120]}")
        if code == 418:
            raise RuntimeError("admin account not verified")
        if code >= 500:
            raise RuntimeError(f"ZT unavailable: HTTP {code}")
        if code != 200:
            raise RuntimeError(f"login failed HTTP {code}: {raw[:120]}")

        code, me, raw = _req(cfg, "GET", cfg.ZT_ME_PATH)
        if code != 200:
            raise RuntimeError(f"cannot fetch {cfg.ZT_ME_PATH}: HTTP {code}")

        admin_id = me.get("id") if isinstance(me, dict) else None
        if not admin_id:
            raise RuntimeError("admin id missing in /users/me")
        _admin_id = int(admin_id)
        return _admin_id


def _request(cfg, method, path, body=None, retry_on_401=True):
    _ensure_admin(cfg)
    code, resp, raw = _req(cfg, method, path, body=body)
    if code == 401 and retry_on_401:
        global _admin_id
        with _login_lock:
            _admin_id = None
        _ensure_admin(cfg, force=True)
        code, resp, raw = _req(cfg, method, path, body=body)
    return code, resp, raw


# ============================================================
# Users & Teams
# ============================================================

def _fetch_all_users(cfg):
    global _admin_users_available

    if _admin_users_available is not False:
        code, resp, _ = _request(cfg, "GET", "/admin/users")
        if code == 200:
            _admin_users_available = True
            if isinstance(resp, list):
                return resp
            if isinstance(resp, dict):
                for k in ("data", "users", "items"):
                    if isinstance(resp.get(k), list):
                        return resp[k]
            return []
        if code in (403, 404):
            _admin_users_available = False

    code, resp, _ = _request(cfg, "GET", "/users")
    if code != 200:
        return []
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("data", "users", "items"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def get_user_by_email(cfg, ident):
    target = (ident or "").strip().lower()
    if not target:
        return None

    users = _fetch_all_users(cfg)
    if not users:
        return None

    if getattr(cfg, "ZT_LOGIN_FIELD", "email") == "email":
        fields = ("email", "mail", "user_email")
    else:
        fields = ("name", "username", "nickname")

    for user in users:
        if not isinstance(user, dict):
            continue
        for field in fields:
            candidate = (user.get(field) or "").strip().lower()
            if candidate and candidate == target:
                return user
    return None


def get_team_name(cfg, team_id):
    for path in (f"/admin/teams/{team_id}", f"/teams/{team_id}"):
        code, data, _ = _request(cfg, "GET", path)
        if code != 200 or not isinstance(data, dict):
            continue
        if isinstance(data.get("data"), dict):
            data = data["data"]
        if data.get("name"):
            return str(data["name"])
    return None


# ============================================================
# Solved
# ============================================================

def is_challenge_solved_for_team(cfg, team_id, challenge_name):
    if not team_id or not challenge_name:
        return False
    code, data, _ = _request(
        cfg, "GET", f"/admin/statistics/solves/table/teams/{team_id}")
    if code != 200 or not isinstance(data, dict):
        return False
    challenges = data.get("challenges", [])
    if not isinstance(challenges, list):
        return False
    needle = str(challenge_name).strip().strip("[]").lower()
    for ch in challenges:
        if not isinstance(ch, dict):
            continue
        name = (ch.get("challenge_name") or "").strip().strip("[]").lower()
        status = (ch.get("status") or "").lower()
        if name == needle and status == "pass":
            return True
    return False


is_solved_for_team = is_challenge_solved_for_team


# ============================================================
# Resolve
# ============================================================

def resolve(cfg, ident):
    try:
        user = get_user_by_email(cfg, ident)
        if not user:
            return {"valid": False, "error": "user not found"}

        team_id = user.get("team_id")
        team_name = user.get("team_name")

        if not team_id and not team_name:
            user_id = user.get("id")
            if user_id:
                code, details, _ = _request(cfg, "GET", f"/users/{user_id}")
                if code == 200 and isinstance(details, dict):
                    team_id = details.get("team_id")
                    team_name = details.get("team_name")

        if not team_id and not team_name:
            return {"valid": False, "error": "user has no team"}

        if not team_id and team_name:
            for p in ("/admin/teams", "/teams"):
                code, teams, _ = _request(cfg, "GET", p)
                if code == 200 and isinstance(teams, list):
                    for t in teams:
                        if t.get("name") == team_name:
                            team_id = t.get("id")
                            break
                if team_id:
                    break
            if not team_id:
                team_id = zlib.crc32(team_name.encode()) & 0xffffffff

        if team_id and not team_name:
            team_name = get_team_name(cfg, team_id) or ""

        return {
            "valid": True,
            "team_id": int(team_id),
            "team_name": str(team_name),
            "user_id": int(user.get("id")),
        }
    except Exception as e:
        return {"valid": False, "error": f"zerotrace: {e}"}


# ============================================================
# Probe
# ============================================================

def probe(cfg, ident):
    print(f"[probe] base={cfg.ZT_BASE_URL}", flush=True)
    print(f"[probe] admin={cfg.ZT_ADMIN_EMAIL or '<empty>'}", flush=True)

    try:
        aid = _ensure_admin(cfg, force=True)
        print(f"[probe] admin id = {aid}", flush=True)
    except Exception as e:
        print(f"[probe] login failed: {e}", flush=True)
        return

    if ident:
        user = get_user_by_email(cfg, ident)
        if user and user.get("id"):
            uid = user["id"]
            print(f"[probe] GET /users/{uid} …", flush=True)
            code, raw_user, raw_text = _req(cfg, "GET", f"/users/{uid}")
            print(f"[probe]   → {code} {raw_text[:300]}", flush=True)

    print(f"[probe] resolve({ident})", flush=True)
    r = resolve(cfg, ident)
    print(f"[probe]   {r}", flush=True)

    if r.get("valid") and cfg.ZT_CHALLENGE_NAME:
        solved = is_challenge_solved_for_team(cfg, r["team_id"], cfg.ZT_CHALLENGE_NAME)
        print(f"[probe] is_challenge_solved_for_team({r['team_id']}, "
              f"{cfg.ZT_CHALLENGE_NAME}) → {solved}", flush=True)
