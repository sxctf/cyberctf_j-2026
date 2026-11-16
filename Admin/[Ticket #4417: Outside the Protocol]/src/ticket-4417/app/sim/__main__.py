import os
import socket
import threading

from app.common.config import load_config
from app.common.http import http_post
from app.sim.session import Session


def verify_cb(cfg, team_id, email, team_name, sw_state, fw_state):
    state = {"sw": sw_state, "fw": fw_state}
    code, resp = http_post(
        cfg.VERIFY_URL + "/check",
        {
            "team_id": team_id,
            "token": cfg.VERIFY_TOKEN,
            "email": email,
            "team_name": team_name,
            "state": state,
        },
        timeout=cfg.HTTP_TIMEOUT,
    )
    if code != 200:
        reason = (resp.get("reason") or resp.get("error")
                  or f"HTTP {code}, empty body")
        return {"solved": False, "reason": reason}
    return resp


def handle_client(cfg, team_id, email, team_name, conn):
    try:
        conn.sendall("ЛК-2408 CLI. help — помощь\r\n".encode())
    except Exception:
        pass
    try:
        session = Session(
            lambda sw, fw: verify_cb(cfg, team_id, email, team_name, sw, fw)
        )
        buf = b""
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="replace").strip("\r")
                if not text:
                    continue
                outputs = session.handle_line(text)
                for out in outputs:
                    if out == "__DISCONNECT__":
                        try:
                            conn.sendall(b"bye\r\n")
                        except Exception:
                            pass
                        return
                    conn.sendall((out + "\r\n").encode())
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    cfg = load_config()
    team_id = int(os.environ.get("TEAM_ID", "0"))
    email = os.environ.get("EMAIL", "")
    team_name = os.environ.get("TEAM_NAME", "")

    host = "0.0.0.0"
    port = cfg.INTERNAL_PORT
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(16)
    print(f"sim on {host}:{port} team={team_id} email={email}", flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(
            target=handle_client,
            args=(cfg, team_id, email, team_name, conn),
            daemon=True,
        ).start()


if __name__ == "__main__":
    main()