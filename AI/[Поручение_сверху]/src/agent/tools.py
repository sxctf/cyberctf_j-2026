"""Tool implementations for the SWE-agent."""
import asyncio
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

GITEA_URL    = os.environ.get("GITEA_URL", "http://127.0.0.1:8202")
BOT_USER     = os.environ.get("GITEA_BOT_USER", "autofix-bot")
BOT_TOKEN    = os.environ.get("GITEA_BOT_TOKEN", "")
BOT_PASS     = os.environ.get("GITEA_BOT_PASS", "botpass456!")
ORG          = "widgetcorp"
WORKSPACE    = Path(os.environ.get("AGENT_WORKSPACE", "/workspace"))

# Auth for Gitea API
def _auth():
    if BOT_TOKEN:
        return {"Authorization": f"token {BOT_TOKEN}"}
    basic = base64.b64encode(f"{BOT_USER}:{BOT_PASS}".encode()).decode()
    return {"Authorization": f"Basic {basic}"}


# --------------------------------------------------------------------------
# File system tools
# --------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file from the workspace."""
    p = (WORKSPACE / path).resolve()
    # Prevent path traversal outside /workspace
    if not str(p).startswith(str(WORKSPACE)):
        return f"[ERROR] Access denied: {path}"
    try:
        return p.read_text(errors="replace")[:8192]
    except FileNotFoundError:
        return f"[ERROR] File not found: {path}"
    except Exception as e:
        return f"[ERROR] {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file in the workspace."""
    p = (WORKSPACE / path).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        return "[ERROR] Access denied"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"[OK] Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"[ERROR] {e}"


def list_files(path: str = ".") -> str:
    """List files in directory."""
    p = (WORKSPACE / path).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        return "[ERROR] Access denied"
    try:
        items = sorted(p.iterdir())
        lines = []
        for item in items[:50]:
            rel = item.relative_to(WORKSPACE)
            lines.append(f"{'d' if item.is_dir() else 'f'}  {rel}")
        return "\n".join(lines)
    except Exception as e:
        return f"[ERROR] {e}"


# --------------------------------------------------------------------------
# Bash tool (restricted)
# --------------------------------------------------------------------------

def bash(command: str, cwd: str = ".") -> str:
    """Run a bash command in the workspace."""
    work_dir = (WORKSPACE / cwd).resolve()
    if not str(work_dir).startswith(str(WORKSPACE)):
        return "[ERROR] Access denied"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=str(work_dir), timeout=30,
            env={**os.environ, "HOME": os.environ.get("AGENT_HOME", "/tmp"), "GIT_AUTHOR_NAME": "AutoFix Bot",
                 "GIT_AUTHOR_EMAIL": "bot@ctf.local",
                 "GIT_COMMITTER_NAME": "AutoFix Bot",
                 "GIT_COMMITTER_EMAIL": "bot@ctf.local"},
        )
        output = result.stdout + result.stderr
        return output[:4096] or "(no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out"
    except Exception as e:
        return f"[ERROR] {e}"


# --------------------------------------------------------------------------
# Git tools
# --------------------------------------------------------------------------

def git_clone_repos() -> str:
    """Clone both repos to /workspace."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    results = []
    for repo in ("widget-public", "internal-secrets"):
        dest = WORKSPACE / repo
        if dest.exists():
            results.append(f"[OK] {repo} already cloned")
            continue
        auth_url = f"http://{BOT_USER}:{BOT_PASS}@{GITEA_URL.split("//")[-1]}/{ORG}/{repo}.git"
        r = bash(f"git clone {auth_url} {dest}")
        results.append(f"{repo}: {r[:200]}")
    return "\n".join(results)


def git_commit(repo: str, message: str) -> str:
    """Stage all changes and commit in a repo."""
    cwd = str(WORKSPACE / repo)
    r = bash(f"git add -A && git commit -m {repr(message)}", cwd=repo)
    return r


def git_push(repo: str, branch: str = "main") -> str:
    """Push commits to remote."""
    auth_url = f"http://{BOT_USER}:{BOT_PASS}@{GITEA_URL.split("//")[-1]}/{ORG}/{repo}.git"
    r = bash(f"git remote set-url origin {auth_url} && git push origin {branch}", cwd=repo)
    return r


def git_create_branch(repo: str, branch: str) -> str:
    """Create and checkout a new branch."""
    return bash(f"git checkout -b {branch}", cwd=repo)


# --------------------------------------------------------------------------
# Gitea API tools
# --------------------------------------------------------------------------

def gitea_create_pr(repo: str, title: str, body: str, head: str, base: str = "main") -> str:
    """Create a Pull Request on Gitea."""
    with httpx.Client(base_url=GITEA_URL, headers=_auth(), timeout=10) as client:
        r = client.post(f"/api/v1/repos/{ORG}/{repo}/pulls", json={
            "title": title, "body": body,
            "head": head, "base": base,
        })
        if r.status_code in (201, 409):
            return f"[OK] PR created/exists: {title}"
        return f"[ERROR] {r.status_code}: {r.text[:200]}"


def gitea_comment(repo: str, issue_number: int, body: str) -> str:
    """Post a comment on an issue/PR."""
    with httpx.Client(base_url=GITEA_URL, headers=_auth(), timeout=10) as client:
        r = client.post(f"/api/v1/repos/{ORG}/{repo}/issues/{issue_number}/comments",
                        json={"body": body})
        if r.status_code == 201:
            return f"[OK] Comment posted on #{issue_number}"
        return f"[ERROR] {r.status_code}: {r.text[:200]}"


def gitea_create_issue(repo: str, title: str, body: str) -> str:
    """Create a new issue on Gitea."""
    with httpx.Client(base_url=GITEA_URL, headers=_auth(), timeout=10) as client:
        r = client.post(f"/api/v1/repos/{ORG}/{repo}/issues",
                        json={"title": title, "body": body})
        if r.status_code == 201:
            return f"[OK] Issue created: {title}"
        return f"[ERROR] {r.status_code}: {r.text[:200]}"


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------

TOOLS = {
    "read_file":         read_file,
    "write_file":        write_file,
    "list_files":        list_files,
    "bash":              bash,
    "git_clone_repos":   lambda: git_clone_repos(),
    "git_commit":        git_commit,
    "git_push":          git_push,
    "git_create_branch": git_create_branch,
    "gitea_create_pr":   gitea_create_pr,
    "gitea_comment":     gitea_comment,
    "gitea_create_issue":gitea_create_issue,
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from the cloned workspace. Path relative to /workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path relative to /workspace"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write content to a file in the workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List files in a workspace directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "default": "."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a bash command in the workspace. Use for testing, linting, etc.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string", "description": "Working dir relative to /workspace, e.g. 'widget-public'"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "git_clone_repos",
        "description": "Clone both widgetcorp/widget-public and widgetcorp/internal-secrets to /workspace.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "git_commit",
        "description": "Stage all changes and commit in a repo.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string", "description": "Repo name: widget-public or internal-secrets"},
            "message": {"type": "string"},
        }, "required": ["repo", "message"]},
    }},
    {"type": "function", "function": {
        "name": "git_push",
        "description": "Push commits to Gitea remote.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string"}, "branch": {"type": "string", "default": "main"},
        }, "required": ["repo"]},
    }},
    {"type": "function", "function": {
        "name": "git_create_branch",
        "description": "Create and checkout a new branch in a repo.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string"}, "branch": {"type": "string"},
        }, "required": ["repo", "branch"]},
    }},
    {"type": "function", "function": {
        "name": "gitea_create_pr",
        "description": "Create a Pull Request on widget-public.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string"}, "title": {"type": "string"},
            "body": {"type": "string"}, "head": {"type": "string"},
            "base": {"type": "string", "default": "main"},
        }, "required": ["repo", "title", "body", "head"]},
    }},
    {"type": "function", "function": {
        "name": "gitea_comment",
        "description": "Post a comment on an issue or PR in widget-public.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string"}, "issue_number": {"type": "integer"},
            "body": {"type": "string"},
        }, "required": ["repo", "issue_number", "body"]},
    }},
    {"type": "function", "function": {
        "name": "gitea_create_issue",
        "description": "Create a new issue in widget-public.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string"}, "title": {"type": "string"},
            "body": {"type": "string"},
        }, "required": ["repo", "title", "body"]},
    }},
]


def execute_tool(name: str, args: dict) -> str:
    func = TOOLS.get(name)
    if not func:
        return f"[ERROR] Unknown tool: {name}"
    try:
        return str(func(**args))
    except Exception as e:
        return f"[ERROR] Tool {name} raised: {e}"
