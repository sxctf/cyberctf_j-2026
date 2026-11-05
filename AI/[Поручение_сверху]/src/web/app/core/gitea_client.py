"""Gitea API client for the task05 web portal."""
import os
import httpx

GITEA_URL        = os.environ.get("GITEA_URL", "http://127.0.0.1:8202")
GITEA_PUBLIC_URL = os.environ.get("GITEA_PUBLIC_URL", "http://localhost:8202")
ADMIN_USER  = os.environ.get("GITEA_ADMIN_USER", "ctfadmin")
ADMIN_PASS  = os.environ.get("GITEA_ADMIN_PASS", "ctfadmin123!")
BOT_USER    = os.environ.get("GITEA_BOT_USER", "autofix-bot")
BOT_PASS    = os.environ.get("GITEA_BOT_PASS", "botpass456!")
ORG         = "widgetcorp"


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=GITEA_URL, auth=(ADMIN_USER, ADMIN_PASS), timeout=10)


async def create_team_account(team_name: str) -> dict:
    """Create a Gitea user for the team and fork widget-public."""
    username = _sanitize(team_name)
    password = _gen_password(team_name)
    email = f"{username}@ctf.local"

    async with _admin_client() as client:
        # Create user
        r = await client.post("/api/v1/admin/users", json={
            "username": username, "password": password,
            "email": email, "must_change_password": False,
            "login_name": username, "source_id": 0,
        })
        if r.status_code not in (201, 422):
            r.raise_for_status()

        # Fork widget-public as the new user
        user_client = httpx.AsyncClient(base_url=GITEA_URL,
                                         auth=(username, password), timeout=15)
        async with user_client as uc:
            fork_r = await uc.post(f"/api/v1/repos/{ORG}/widget-public/forks",
                                   json={"name": "widget-public"})
            fork_url = ""
            if fork_r.status_code in (202, 409):
                fork_url = f"{GITEA_PUBLIC_URL}/{username}/widget-public"

    return {
        "username": username,
        "password": password,
        "gitea_url": GITEA_PUBLIC_URL,
        "fork_url": fork_url,
    }


async def get_public_comments(repo: str = "widget-public") -> list:
    """Get all comments posted by the bot on issues/PRs in widget-public."""
    async with _admin_client() as client:
        r = await client.get(f"/api/v1/repos/{ORG}/{repo}/issues/comments",
                             params={"limit": 50, "token": ""})
        if r.status_code != 200:
            return []
        return r.json()


async def get_bot_commits(repo: str = "widget-public") -> list:
    """Get recent commits pushed by the bot."""
    async with _admin_client() as client:
        r = await client.get(f"/api/v1/repos/{ORG}/{repo}/commits",
                             params={"limit": 20})
        if r.status_code != 200:
            return []
        return r.json()


async def get_issues(repo: str = "widget-public", state: str = "open") -> list:
    async with _admin_client() as client:
        r = await client.get(f"/api/v1/repos/{ORG}/{repo}/issues",
                             params={"state": state, "type": "issues", "limit": 20})
        return r.json() if r.status_code == 200 else []


def _sanitize(name: str) -> str:
    import re
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower())[:32]
    return safe or "team"


def _gen_password(seed: str) -> str:
    import hashlib
    h = hashlib.sha256(f"ctf-salt-{seed}".encode()).hexdigest()[:12]
    return f"P{h}!"
