import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request


app = Flask(__name__, static_folder="public", static_url_path="/public")

PREMIERE_AT = datetime(2026, 12, 25, 18, 0, 0, tzinfo=timezone.utc)
PUBLIC_DIR = Path("/app/public")
SECRET_DIR = Path("/app/secret")
FLAG_PATH = SECRET_DIR / "flag.txt"
FLAG = os.environ.get("FLAG", "flag{THIS_IS_FAKE_FLAG}")


def materialize_flag() -> None:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    FLAG_PATH.write_text(f"{FLAG}\n", encoding="utf-8")


materialize_flag()


def get_countdown():
    now = datetime.now(timezone.utc)
    diff = PREMIERE_AT - now
    total_seconds = int(diff.total_seconds())
    if total_seconds < 0:
        total_seconds = 0

    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return {
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "premiere_utc": PREMIERE_AT.isoformat(),
    }


@app.get("/")
def index():
    return render_template("index.html", countdown=get_countdown())


@app.get("/api/countdown")
def countdown():
    return jsonify(get_countdown())


@app.post("/api/wish")
def wish():
    payload = request.get_data(as_text=True) or ""
    content_type = request.headers.get("Content-Type", "")
    requested_path = payload.strip()

    if not requested_path:
        return jsonify(
            {
                "status": "empty",
                "message": "Передай путь к файлу в теле запроса.",
                "content_type": content_type,
            }
        )

    target_path = os.path.join(str(PUBLIC_DIR), requested_path)
    try:
        with open(target_path, "rb") as file:
            file_content = file.read()
            decoded_content = file_content.decode("utf-8")
    except FileNotFoundError:
        return jsonify(
            {
                "status": "not_found",
                "message": "Файл не найден.",
                "requested_path": requested_path,
                "content_type": content_type,
            }
        )
    except IsADirectoryError:
        return jsonify(
            {
                "status": "invalid",
                "message": "Путь указывает на директорию.",
                "requested_path": requested_path,
                "content_type": content_type,
            }
        )
    except UnicodeDecodeError:
        return jsonify(
            {
                "status": "binary",
                "message": "Файл не текстовый.",
                "requested_path": requested_path,
                "content_type": content_type,
                "size_bytes": len(file_content),
            }
        )
    except OSError as err:
        return jsonify(
            {
                "status": "error",
                "message": str(err),
                "requested_path": requested_path,
                "content_type": content_type,
            }
        )

    return jsonify(
        {
            "status": "ok",
            "message": "Файл прочитан.",
            "content_type": content_type,
            "requested_path": requested_path,
            "content": decoded_content,
        }
    )


@app.get("/healthz")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
