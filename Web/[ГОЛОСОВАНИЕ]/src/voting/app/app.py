import os
import re
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "ctf.db")
ROUND_INTERVAL_SECONDS = int(os.environ.get("ROUND_INTERVAL_SECONDS", "600"))
GUEST_VOTER_COOKIE = "voter_id"
VIEW_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS story_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_story TEXT NOT NULL,
            current_round INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            round_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            view_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            voter_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (suggestion_id, voter_token),
            FOREIGN KEY (suggestion_id) REFERENCES suggestions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS story_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER,
            round_number INTEGER NOT NULL,
            selected_text TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
        );

        CREATE TABLE IF NOT EXISTS idea_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            view_key TEXT NOT NULL,
            viewer TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    now = utc_now()
    db.execute(
        """
        INSERT OR IGNORE INTO story_state (id, current_story, current_round, updated_at)
        VALUES (1, ?, 1, ?)
        """,
        (
            "В Лаборатории главный герой Руби нашел волшебный карандаш,"
            " который оживляет любой нарисованный объект.",
            now,
        ),
    )
    db.execute(
        """
        INSERT OR IGNORE INTO users (id, username, password_hash, created_at)
        VALUES (0, 'guest', '!', ?)
        """,
        (now,),
    )
    migrate_votes_schema(db)
    migrate_idea_views_schema(db)
    db.commit()
    db.close()


def new_view_key():
    return uuid.uuid4().hex


def migrate_idea_views_schema(db):
    suggestion_cols = {row[1] for row in db.execute("PRAGMA table_info(suggestions)").fetchall()}
    if suggestion_cols and "view_key" not in suggestion_cols:
        db.execute("ALTER TABLE suggestions ADD COLUMN view_key TEXT")
    missing = db.execute(
        "SELECT id FROM suggestions WHERE view_key IS NULL OR view_key = ''"
    ).fetchall()
    for row in missing:
        db.execute("UPDATE suggestions SET view_key = ? WHERE id = ?", (new_view_key(), row[0]))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestions_view_key ON suggestions(view_key)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS idea_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            view_key TEXT NOT NULL,
            viewer TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_idea_views_key ON idea_views(view_key)")
    db.execute("DROP TABLE IF EXISTS guestbook")


def migrate_votes_schema(db):
    columns = {row[1] for row in db.execute("PRAGMA table_info(votes)").fetchall()}
    if not columns or "voter_token" in columns:
        return
    db.executescript(
        """
        CREATE TABLE votes_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            voter_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (suggestion_id, voter_token),
            FOREIGN KEY (suggestion_id) REFERENCES suggestions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        INSERT INTO votes_new (id, suggestion_id, user_id, voter_token, created_at)
        SELECT id, suggestion_id, user_id, voter_ip, created_at FROM votes;
        DROP TABLE votes;
        ALTER TABLE votes_new RENAME TO votes;
        """
    )


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def get_voter_token():
    user_id = session.get("user_id")
    if user_id:
        return f"user:{user_id}"

    voter_id = session.get("voter_id") or request.cookies.get(GUEST_VOTER_COOKIE)
    if not voter_id:
        voter_id = uuid.uuid4().hex
    session["voter_id"] = voter_id
    g.guest_voter_id = voter_id
    return f"guest:{voter_id}"


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Сначала войдите в систему.")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


def get_story_state(db):
    return db.execute("SELECT * FROM story_state WHERE id = 1").fetchone()


def get_current_user(db):
    if "user_id" not in session:
        return None
    return db.execute(
        "SELECT id, username FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()


def has_voted_this_round(db, round_number, voter_token=None):
    if voter_token is None:
        voter_token = get_voter_token()
    return (
        db.execute(
            """
            SELECT v.id
            FROM votes v
            JOIN suggestions s ON s.id = v.suggestion_id
            WHERE s.round_number = ? AND v.voter_token = ?
            LIMIT 1
            """,
            (round_number, voter_token),
        ).fetchone()
        is not None
    )


def finish_round():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    state = db.execute("SELECT * FROM story_state WHERE id = 1").fetchone()
    round_number = state["current_round"]

    winner = db.execute(
        """
        SELECT s.id, s.content, COALESCE(COUNT(v.id), 0) AS vote_count
        FROM suggestions s
        LEFT JOIN votes v ON v.suggestion_id = s.id
        WHERE s.round_number = ? AND s.status = 'pending'
        GROUP BY s.id
        ORDER BY vote_count DESC, s.created_at ASC
        LIMIT 1
        """,
        (round_number,),
    ).fetchone()

    now = utc_now()
    if winner:
        db.execute(
            "UPDATE suggestions SET status = 'winner' WHERE id = ?",
            (winner["id"],),
        )
        db.execute(
            """
            UPDATE suggestions
            SET status = 'rejected'
            WHERE round_number = ? AND status = 'pending' AND id != ?
            """,
            (round_number, winner["id"]),
        )
        updated_story = state["current_story"] + "\n" + winner["content"]
        db.execute(
            """
            INSERT INTO story_history (suggestion_id, round_number, selected_text, selected_at)
            VALUES (?, ?, ?, ?)
            """,
            (winner["id"], round_number, winner["content"], now),
        )
    else:
        updated_story = state["current_story"] + "\n(Раунд завершен без новых идей.)"
        db.execute(
            """
            INSERT INTO story_history (suggestion_id, round_number, selected_text, selected_at)
            VALUES (NULL, ?, ?, ?)
            """,
            (round_number, "(Раунд завершен без новых идей.)", now),
        )

    db.execute(
        """
        UPDATE story_state
        SET current_story = ?, current_round = current_round + 1, updated_at = ?
        WHERE id = 1
        """,
        (updated_story, now),
    )
    db.commit()
    db.close()


def reject_direct_tags(value):
    if re.search(r"<[a-zA-Z]", value):
        return True
    return False


@app.after_request
def add_response_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https://www.google.com https://www.gstatic.com "
        "https://ajax.googleapis.com https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com https://fonts.gstatic.com data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:;"
    )
    guest_voter_id = getattr(g, "guest_voter_id", None)
    if guest_voter_id:
        response.set_cookie(
            GUEST_VOTER_COOKIE,
            guest_voter_id,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="Lax",
        )
    return response


@app.route("/", methods=["GET"])
def index():
    db = get_db()
    state = get_story_state(db)
    round_number = state["current_round"]
    suggestions = db.execute(
        """
        SELECT
            s.id,
            s.content,
            s.created_at,
            u.username,
            COALESCE(COUNT(v.id), 0) AS vote_count
        FROM suggestions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN votes v ON v.suggestion_id = s.id
        WHERE s.round_number = ? AND s.status = 'pending'
        GROUP BY s.id
        ORDER BY vote_count DESC, s.created_at ASC
        """,
        (round_number,),
    ).fetchall()

    history = db.execute(
        """
        SELECT round_number, selected_text, selected_at
        FROM story_history
        ORDER BY round_number DESC
        LIMIT 10
        """
    ).fetchall()

    user = get_current_user(db)
    voted_this_round = has_voted_this_round(db, round_number)
    user_has_suggestion = False
    if user:
        user_has_suggestion = (
            db.execute(
                """
                SELECT id
                FROM suggestions
                WHERE user_id = ? AND round_number = ? AND status = 'pending'
                LIMIT 1
                """,
                (user["id"], round_number),
            ).fetchone()
            is not None
        )

    return render_template(
        "index.html",
        story=state["current_story"],
        current_round=round_number,
        suggestions=suggestions,
        history=history,
        user=user,
        user_has_suggestion=user_has_suggestion,
        voted_this_round=voted_this_round,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Введите username и password.")
        return redirect(url_for("register"))

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (username, generate_password_hash(password), utc_now()),
        )
        db.commit()
        flash("Регистрация успешна. Теперь войдите.")
    except sqlite3.IntegrityError:
        flash("Пользователь с таким логином уже существует.")
        return redirect(url_for("register"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    db = get_db()
    user = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Неверный логин или пароль.")
        return redirect(url_for("login"))

    session["user_id"] = user["id"]
    flash(f"Вход выполнен: {user['username']}")
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    voter_id = session.get("voter_id") or request.cookies.get(GUEST_VOTER_COOKIE)
    session.clear()
    if voter_id:
        session["voter_id"] = voter_id
        g.guest_voter_id = voter_id
    flash("Вы вышли из аккаунта.")
    return redirect(url_for("index"))


@app.route("/suggest", methods=["POST"])
@login_required
def suggest():
    content = request.form.get("content", "").strip()
    if not content:
        flash("Идея не может быть пустой.")
        return redirect(url_for("suggest_page"))
    if len(content) > 500:
        flash("Идея слишком длинная (максимум 500 символов).")
        return redirect(url_for("suggest_page"))

    db = get_db()
    round_number = get_story_state(db)["current_round"]
    existing_suggestion = db.execute(
        """
        SELECT id
        FROM suggestions
        WHERE user_id = ? AND round_number = ? AND status = 'pending'
        LIMIT 1
        """,
        (session["user_id"], round_number),
    ).fetchone()
    if existing_suggestion:
        flash("Вы уже добавили идею в текущем раунде.")
        return redirect(url_for("suggest_page"))

    db.execute(
        """
        INSERT INTO suggestions (user_id, content, round_number, status, view_key, created_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (session["user_id"], content, round_number, new_view_key(), utc_now()),
    )
    db.commit()
    flash("Идея добавлена в текущий раунд голосования.")
    return redirect(url_for("suggest_page"))


@app.route("/suggest/new", methods=["GET"])
@login_required
def suggest_page():
    db = get_db()
    user = get_current_user(db)
    round_number = get_story_state(db)["current_round"]
    my_suggestion = db.execute(
        """
        SELECT id, content, created_at, view_key
        FROM suggestions
        WHERE user_id = ? AND round_number = ? AND status = 'pending'
        LIMIT 1
        """,
        (user["id"], round_number),
    ).fetchone()
    return render_template(
        "suggest.html",
        user=user,
        current_round=round_number,
        my_suggestion=my_suggestion,
    )


@app.route("/suggest/<int:suggestion_id>/delete", methods=["POST"])
@login_required
def delete_suggestion(suggestion_id):
    db = get_db()
    round_number = get_story_state(db)["current_round"]
    suggestion = db.execute(
        """
        SELECT id, view_key
        FROM suggestions
        WHERE id = ? AND user_id = ? AND round_number = ? AND status = 'pending'
        """,
        (suggestion_id, session["user_id"], round_number),
    ).fetchone()
    if not suggestion:
        flash("Нельзя удалить эту идею.")
        return redirect(url_for("suggest_page"))

    db.execute("DELETE FROM votes WHERE suggestion_id = ?", (suggestion_id,))
    db.execute("DELETE FROM idea_views WHERE view_key = ?", (suggestion["view_key"],))
    db.execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
    db.commit()
    flash("Идея удалена.")
    return redirect(url_for("suggest_page"))


@app.route("/vote", methods=["GET"])
def vote_page():
    db = get_db()
    state = get_story_state(db)
    round_number = state["current_round"]
    user = get_current_user(db)
    suggestions = db.execute(
        """
        SELECT
            s.id,
            s.content,
            s.created_at,
            u.username,
            COALESCE(COUNT(v.id), 0) AS vote_count
        FROM suggestions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN votes v ON v.suggestion_id = s.id
        WHERE s.round_number = ? AND s.status = 'pending'
        GROUP BY s.id
        ORDER BY vote_count DESC, s.created_at ASC
        """,
        (round_number,),
    ).fetchall()
    voted_this_round = has_voted_this_round(db, round_number)
    return render_template(
        "vote.html",
        user=user,
        current_round=round_number,
        suggestions=suggestions,
        voted_this_round=voted_this_round,
    )


@app.route("/vote/<int:suggestion_id>", methods=["POST"])
def vote(suggestion_id):
    db = get_db()
    state = get_story_state(db)
    voter_token = get_voter_token()
    suggestion = db.execute(
        """
        SELECT id
        FROM suggestions
        WHERE id = ? AND round_number = ? AND status = 'pending'
        """,
        (suggestion_id, state["current_round"]),
    ).fetchone()
    if not suggestion:
        flash("Эта идея недоступна для голосования.")
        return redirect(url_for("vote_page"))

    if has_voted_this_round(db, state["current_round"], voter_token):
        flash("Вы уже голосовали в этом раунде.")
        return redirect(url_for("vote_page"))

    voter_user_id = session.get("user_id", 0)
    try:
        db.execute(
            """
            INSERT INTO votes (suggestion_id, user_id, voter_token, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (suggestion_id, voter_user_id, voter_token, utc_now()),
        )
        db.commit()
        flash("Голос принят.")
    except sqlite3.IntegrityError:
        flash("Вы уже голосовали в этом раунде.")
    return redirect(url_for("vote_page"))


@app.route("/story-lab", methods=["GET"])
def story_lab():
    firstname = request.args.get("firstname", "")
    lastname = request.args.get("lastname", "")
    email = request.args.get("email", "")

    if reject_direct_tags(firstname) or reject_direct_tags(lastname) or reject_direct_tags(email):
        return "An error occurred", 500

    return render_template(
        "story_lab.html",
        firstname=firstname,
        lastname=lastname,
        email=email,
    )


@app.route("/report", methods=["GET", "POST"])
def report():
    target_url = request.form.get("url") if request.method == "POST" else request.args.get("url")
    if not target_url:
        return "Missing url", 400

    if target_url.startswith("/"):
        target_url = f"http://web:5000{target_url}"
    try:
        response = requests.post("http://bot:3000/visit", json={"url": target_url}, timeout=10)
        return f"Report sent: {response.text}"
    except Exception as exc:
        return f"Error: {exc}", 500


def get_suggestion_by_view_key(db, view_key):
    return db.execute(
        """
        SELECT id, user_id, content, view_key
        FROM suggestions
        WHERE view_key = ?
        """,
        (view_key,),
    ).fetchone()


def add_idea_view(db, view_key, viewer):
    viewer = (viewer or "").strip()
    if not viewer:
        return
    db.execute(
        "INSERT INTO idea_views (view_key, viewer, created_at) VALUES (?, ?, ?)",
        (view_key, viewer[:2000], utc_now()),
    )
    db.commit()


@app.route("/views/<key>", methods=["GET", "POST"])
def idea_views(key):
    if not VIEW_KEY_RE.fullmatch(key):
        return "Not found", 404

    db = get_db()
    suggestion = get_suggestion_by_view_key(db, key)
    if not suggestion:
        return "Not found", 404

    if request.method == "POST":
        add_idea_view(db, key, request.form.get("viewer", ""))
        return redirect(url_for("idea_views", key=key))

    add_idea_view(db, key, request.args.get("viewer", ""))
    visitors = db.execute(
        """
        SELECT viewer, created_at
        FROM idea_views
        WHERE view_key = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (key,),
    ).fetchall()
    return render_template(
        "views.html",
        suggestion=suggestion,
        visitors=visitors,
        view_key=key,
    )


def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(finish_round, "interval", seconds=ROUND_INTERVAL_SECONDS, id="round_job")
    scheduler.start()


if __name__ == "__main__":
    init_db()
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)