"""Runs picklescan 0.0.30 on a file and returns verdict + detail."""
import asyncio
import re
import subprocess
import sys
from pathlib import Path


async def run_picklescan(file_path: str) -> tuple[str, str]:
    """
    Run picklescan on file_path.
    Returns (verdict, detail) where verdict is 'clean' or 'blocked'.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "picklescan", "--path", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace")

        # picklescan 0.0.30 may exit 0 even when it reports infected files
        # (CLI quirk), so the output text is authoritative as well.
        infected = (
            "Infected files: 0" not in output
            and ("dangerous" in output.lower() or "Infected files: 1" in output)
        )
        if proc.returncode == 0 and not infected:
            return "clean", output.strip()
        else:
            # Extract the dangerous global that was found
            detail = _extract_blocked_reason(output)
            return "blocked", detail

    except asyncio.TimeoutError:
        return "blocked", "Scanner timed out"
    except Exception as e:
        return "blocked", f"Scanner error: {e}"


def _extract_blocked_reason(output: str) -> str:
    """Parse picklescan output to extract the reason for blocking."""
    lines = output.strip().splitlines()
    reasons = []
    for line in lines:
        if any(kw in line for kw in ("dangerous", "unsafe", "blocked", "global", "Global", "Error")):
            reasons.append(line.strip())
    if reasons:
        return "\n".join(reasons[:5])
    # Fallback: return last meaningful line
    non_empty = [l.strip() for l in lines if l.strip()]
    return non_empty[-1] if non_empty else output[:500]
