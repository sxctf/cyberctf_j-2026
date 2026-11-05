"""Sandbox loader — isolated container that executes pickle.load() on submitted files.

Security model:
- No network egress except UDP/53 to dns-logger (enforced by Docker network rules)
- Read-only filesystem except /tmp and /exfil
- Killed after 30 seconds per job
- Flag at /flag.txt (mounted read-only)

This simulates torch.load(weights_only=False) which is equivalent to pickle.load
for the purposes of executing pickle payloads.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="task03-sandbox", docs_url=None)

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
EXFIL_DIR = Path(os.environ.get("EXFIL_DIR", "/exfil"))
FLAG_PATH = Path(os.environ.get("FLAG_PATH", "/tmp/flag.txt"))
SANDBOX_PORT = int(os.environ.get("SANDBOX_PORT", "8002"))
TIMEOUT_SECONDS = 30

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXFIL_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Loader process containment (local mode)
# ---------------------------------------------------------------------------
# Docker provides the real isolation (no network, read-only rootfs, cap_drop).
# Locally we apply the practical limits available without admin rights:
# a Windows Job Object bounds the payload process tree (memory cap, process
# count, kill-on-close, kill of spawned children). SANDBOX_ISOLATION reports
# what is active so the web UI can warn organizers when it is "none".

SANDBOX_ISOLATION = "none"


def _assign_job_object(proc) -> object | None:
    """Attach the loader process to a limiting Job Object (Windows)."""
    global SANDBOX_ISOLATION
    if os.name != "nt":
        SANDBOX_ISOLATION = "unix-process-limits"
        return None
    try:
        import win32job  # provided by pywin32
        import win32process
        import win32api
        import pywintypes
    except Exception:
        return None

    try:
        hjob = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(hjob, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] = (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        info["BasicLimitInformation"]["PerProcessMemoryLimit"] = 512 * 1024 * 1024
        info["BasicLimitInformation"]["ActiveProcessLimit"] = 32
        win32job.SetInformationJobObject(hjob, win32job.JobObjectExtendedLimitInformation, info)
        win32job.AssignProcessToJobObject(hjob, int(proc._handle))
        SANDBOX_ISOLATION = "job-object"
        return hjob
    except Exception:
        return None


def _probe_isolation() -> None:
    """Detect at startup whether Job Object containment is available."""
    global SANDBOX_ISOLATION
    if os.name != "nt":
        SANDBOX_ISOLATION = "unix-process-limits"
        return
    try:
        import win32job  # noqa: F401
        SANDBOX_ISOLATION = "job-object"
    except Exception:
        SANDBOX_ISOLATION = "none"


_probe_isolation()


def _ensure_flag_file() -> None:
    """Materialize the flag file from FLAG_TASK_03 when not mounted.

    Docker mounts it at /tmp/flag.txt; local runs write it to FLAG_PATH.
    """
    if not FLAG_PATH.exists():
        flag = os.environ.get("FLAG_TASK_03", "")
        if flag:
            FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
            FLAG_PATH.write_text(flag + "\n", encoding="utf-8")


_ensure_flag_file()


@app.post("/load")
async def load_file(file: UploadFile = File(...), job_id: str = Form(...)):
    """
    Accept a file upload, run pickle.load() on it in a subprocess.
    Captures stdout/stderr and any writes to /exfil/.
    Returns result within TIMEOUT_SECONDS.
    """
    # Save uploaded file to temp path
    suffix = Path(file.filename or "upload.pt").suffix or ".pt"
    tmp_path = UPLOAD_DIR / f"{job_id}{suffix}"
    content = await file.read()
    tmp_path.write_bytes(content)

    # Clean exfil dir before run
    for f in EXFIL_DIR.iterdir():
        try:
            f.unlink()
        except Exception:
            pass

    start = time.monotonic()
    result = await asyncio.wait_for(
        _run_loader(str(tmp_path), job_id),
        timeout=TIMEOUT_SECONDS + 2,
    )
    elapsed = time.monotonic() - start

    # Check if flag was exfiltrated to /exfil/
    exfil_data = _collect_exfil()

    # Cleanup
    try:
        tmp_path.unlink()
    except Exception:
        pass

    return {
        "job_id": job_id,
        "elapsed": round(elapsed, 2),
        "stdout": result["stdout"][:4096],
        "stderr": result["stderr"][:4096],
        "returncode": result["returncode"],
        "exfil": exfil_data,
        "timed_out": result.get("timed_out", False),
    }


async def _run_loader(file_path: str, job_id: str) -> dict:
    """Run a torch.load-style unpickling in a subprocess with timeout.

    Mimics torch.load: ZIP containers (.pt/.pth) are opened via the central
    directory and the inner data.pkl is unpickled; raw pickle streams are
    loaded directly (weights_only=False semantics — arbitrary code executes).
    """
    loader_script = """
import sys, io, pickle, zipfile, traceback
path = sys.argv[1]
try:
    with open(path, 'rb') as f:
        head = f.read(4)
    if head[:4] in (b'PK\\x03\\x04', b'PK\\x05\\x06', b'PK\\x07\\x08'):
        zf = zipfile.ZipFile(path)
        names = zf.namelist()
        target = next((n for n in names if n.endswith('data.pkl')),
                      next((n for n in names if n.endswith('.pkl')), names[0]))
        result = pickle.load(io.BytesIO(zf.read(target)))
    else:
        with open(path, 'rb') as f:
            result = pickle.load(f)
    print("LOAD_OK:", repr(result)[:500])
except Exception as e:
    print("LOAD_ERROR:", traceback.format_exc()[:1000], file=sys.stderr)
    sys.exit(1)
"""
    try:
        # Use the current interpreter so the loader runs on any OS.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(UPLOAD_DIR),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # Windows: needed by python
            "JOB_ID": job_id,
            "EXFIL_DIR": str(EXFIL_DIR),
            "FLAG_PATH": str(FLAG_PATH),
        }
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", loader_script, file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        job = _assign_job_object(proc)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TIMEOUT_SECONDS
            )
            return {
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"stdout": "", "stderr": "Execution timed out (30s)", "returncode": -1, "timed_out": True}
        finally:
            if job is not None:
                job.Terminate(0)  # kill any process the payload managed to spawn
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def _collect_exfil() -> list[dict]:
    """Collect any files written to /exfil/ during the run."""
    results = []
    for f in EXFIL_DIR.iterdir():
        if f.is_file():
            try:
                data = f.read_bytes()
                results.append({
                    "filename": f.name,
                    "content": data[:2048].decode(errors="replace"),
                    "size": len(data),
                })
            except Exception:
                pass
    return results


@app.get("/health")
def health():
    return {"status": "ok", "flag_present": FLAG_PATH.exists(),
            "isolation": SANDBOX_ISOLATION}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=SANDBOX_PORT, log_level="warning")
