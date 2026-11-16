import os

DEFAULTS = {
    "LISTEN_ADDR": "0.0.0.0:7777",
    "FORK_IMAGE": "qubiq-ctf:latest",
    "INTERNAL_PORT": 7777,
    "FORK_TTL": 1800,
    "REAPER_INTERVAL": 30,
    "HANDSHAKE_TIMEOUT": 30,
    "HANDSHAKE_PROMPT": "gate - введите e-mail участника:",
    "STATE_DIR": "/app/state",
    "FORK_NETWORK": "ladoga-net",
    "TEAM_MAX_PER_10MIN": 3,
    "IP_MAX_PER_10MIN": 5,
    "MAX_CONCURRENT": 100,
    "RESOURCE_THRESHOLD": 0.90,
    "METRICS_INTERVAL": 5,
    "MIN_FREE_RAM_MB": 512,
    "MIN_FREE_DISK_MB": 2048,

    # === RESOLVE ===
    "RESOLVE_MODE": "env",
    "RESOLVE_URL": "http://auth:8080/resolve",
    "HTTP_TIMEOUT": 5,
    "USERS": "",

    # === ZEROTRACE ===
    "ZT_BASE_URL": "https://zerotrace.jeopardy.ctflab.local/api/v1",
    "ZT_HOST": "",
    "ZT_INSECURE": "true",
    "ZT_LOGIN_PATH": "/auth/login",
    "ZT_LOGIN_EMAIL_FIELD": "email",
    "ZT_LOGIN_PASSWORD_FIELD": "password",
    "ZT_ME_PATH": "/users/me",
    "ZT_LOGIN_FIELD": "email",          # email | name
    "ZT_ADMIN_EMAIL": "",
    "ZT_ADMIN_PASSWORD": "",
    "ZT_CHALLENGE_NAME": "",

    # === FLAGS ===
    "STATIC_FLAG": "",
    "FLAG_MODE": "file",
    "FLAG_POOL": "/app/state/flags.pool",
    "FLAG_USED": "/app/state/flags.used",
    "FLAG_ASSIGNED": "/app/state/flags.assigned",
    "FLAG_ISSUE_TOKEN": "",
    "FLAG_HTTP_ADDR": "0.0.0.0:7788",

    # === ADMIN ===
    "ADMIN_ADDR": "0.0.0.0:7789",
    "ADMIN_TOKEN": "",

    # === VERIFY ===
    "VERIFY_URL": "http://verify:8081",
    "VERIFY_ADDR": "0.0.0.0:8081",
    "VERIFY_TOKEN": "",
    "GATEWAY_INTERNAL": "http://gateway:7788",

    # === AUTH ===
    "AUTH_ADDR": "0.0.0.0:8080",
    "USERS_FILE": "/app/auth-data/users.json",
    "TEAMS_FILE": "/app/auth-data/teams.json",

    # === SIM ===
    "SW_PASSWORD": "Kr3st-SW-2408",
    "FW_PASSWORD": "Kr3st-FW-2408",

    "DOCKER_EXTRA_ARGS": (
        "--memory 128m --memory-swap 128m --cpus 0.25 "
        "--pids-limit 64 --read-only --tmpfs /tmp:size=16m"
    ),
}

INT_KEYS = {
    "INTERNAL_PORT", "FORK_TTL", "REAPER_INTERVAL", "HANDSHAKE_TIMEOUT",
    "TEAM_MAX_PER_10MIN", "IP_MAX_PER_10MIN", "MAX_CONCURRENT",
    "METRICS_INTERVAL", "MIN_FREE_RAM_MB", "MIN_FREE_DISK_MB", "HTTP_TIMEOUT",
    "ZT_TOKEN_TTL",
}
FLOAT_KEYS = {"RESOURCE_THRESHOLD"}
BOOL_KEYS = {"ZT_INSECURE"}


class Config:
    def __init__(self, values):
        for k, default in DEFAULTS.items():
            v = values.get(k, default)
            if k in INT_KEYS:
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    v = default
            elif k in FLOAT_KEYS:
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = default
            elif k in BOOL_KEYS:
                v = str(v).lower() in ("1", "true", "yes", "on")
            setattr(self, k, v)


def load_config(env_file=None):
    env_file = env_file or os.environ.get("CONFIG_FILE", "/app/config.env")
    values = dict(DEFAULTS)
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line or line.lstrip().startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    for k in DEFAULTS:
        if k in os.environ:
            values[k] = os.environ[k]
    return Config(values)