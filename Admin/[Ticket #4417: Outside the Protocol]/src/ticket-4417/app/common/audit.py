import json
import os
import threading
import time

_lock = threading.Lock()


def audit(state_dir, event, **fields):
    rec = {"ts": int(time.time()), "event": event, **fields}
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    path = os.path.join(state_dir, "audit.log")
    with _lock:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass