import os, sys, uuid, json, shutil
sys.path.insert(0, os.path.dirname(__file__))
from functools import wraps
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, Response, stream_with_context
from agents.validator import ai_review_stream
from core.agent_tools import register_skill, reject_skill, get_db, register_user, authenticate_user
from core.upload import load_skill
from agents.main_agent import main_agent
from logging_config import logger_auth, logger_skills, logger_code, logger_chat

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'tmp', 'uploads')
app.config['SKILLS_DIR'] = os.path.join(os.path.dirname(__file__), 'tmp', 'skills')
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

os.makedirs(os.path.join(os.path.dirname(__file__), 'tmp'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SKILLS_DIR'], exist_ok=True)

# Initialize database
# migrate_db()
get_db().close()


# ── Robots.txt ──

@app.route('/robots.txt')
def robots_txt():
    return """User-agent: *
# Emergency protocol v2.1 — skill loader interface
# Available for authorized personnel only
Disallow: /skill-review

# Working endpoints
Allow: /login
Allow: /register
Allow: /chat
""", 200, {'Content-Type': 'text/plain'}


# ── Auth decorator ──

def require_auth(f):
    """Decorator to protect routes — requires logged-in user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_uuid = session.get('user_uuid')
        if user_uuid is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Auth pages ──

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_uuid') is not None:
        return redirect(url_for('chat'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        success, user_uuid = authenticate_user(username, password)
        if success:
            session['user_uuid'] = user_uuid
            session.permanent = True
            logger_auth.info(f"Login successful", extra={'detail': f"username={username}"})
            return redirect(url_for('chat'))
        else:
            logger_auth.warning(f"Login failed", extra={'detail': f"username={username}"})
            error = 'Неверное имя пользователя или пароль'

    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_uuid') is not None:
        return redirect(url_for('chat'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if password != confirm:
            error = 'Пароли не совпадают'
        else:
            success, user_uuid = register_user(username, password)
            if success:
                session['user_uuid'] = user_uuid
                logger_auth.info(f"User registered", extra={'detail': f"username={username}"})
                return redirect(url_for('chat'))
            else:
                logger_auth.warning(f"Registration failed", extra={'detail': f"username={username}"})
                error = "Ошибка регистрации"

    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    user_uuid = session.get('user_uuid')
    session.clear()
    if user_uuid:
        logger_auth.info(f"User logged out", extra={'detail': f"user_uuid={user_uuid}"})
    return redirect(url_for('login'))


# ── Pages ──

@app.route('/')
@require_auth
def chat():
    return render_template('chat.html')


@app.route('/skill-review')
@require_auth
def review():
    return render_template('index.html')

# ── Tech endpoint ──

@app.route('/skill-stats-info', methods=['GET'])
def skill_stats_info():
    try:
        conn = get_db()
        
        # Total count
        cur = conn.execute("SELECT COUNT(*) FROM skill_registry")
        total = cur.fetchone()[0]
        
        # Success/rejected breakdown
        cur = conn.execute("SELECT status, COUNT(*) FROM skill_registry GROUP BY status")
        breakdown = dict(cur.fetchall())
        
        # Full list with details
        cur = conn.execute("""
            SELECT r.skill_id, r.status, r.registered_at, d.name, d.description, d.version
            FROM skill_registry r
            LEFT JOIN skill_details d ON r.skill_id = d.skill_id
            ORDER BY r.registered_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        skills = []
        for skill_id, status, registered_at, name, description, version in rows:
            skills.append({
                "skill_id": skill_id,
                "status": status,
                "name": name or "Unknown",
                "description": description or "",
                "version": version or "1.0",
                "registered_at": registered_at,
            })
        
        return jsonify({
            "total": total,
            "breakdown": breakdown,
            "skills": skills,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Chat endpoint ──

@app.route('/chat', methods=['POST'])
@require_auth
def chat_full():
    """Sync chat endpoint — returns full response at once."""
    data = request.get_json()
    if not data or not data.get('message'):
        return jsonify({'error': 'No message provided'}), 400

    user_message = data['message']
    history = data.get('history', [])
    user_uuid = session.get('user_uuid', '')

    try:
        result = main_agent(user_message, user_uuid, history)

        if not result.get('success'):
            logger_chat.warning(f"Chat agent failed", extra={'detail': f"user_uuid={user_uuid} message={user_message}"})
            return jsonify({'type': 'error', 'error': result.get('reason', 'Ошибка агента')}), 200

        full_text = result.get('text', '')
        logger_chat.info(f"Chat response sent", extra={'detail': f"user_uuid={user_uuid} message={user_message!r} response_len={len(full_text)}"})

        return jsonify({
            'type': 'ok',
            'text': full_text,
            'history': history + [
                {'role': 'user', 'content': user_message},
                {'role': 'assistant', 'content': full_text},
            ],
        })

    except Exception as e:
        app.logger.exception('chat failed')
        return jsonify({'type': 'error', 'error': str(e)}), 500


# ── Upload endpoints ──


@app.route('/skill-stream-review', methods=['POST'])
@require_auth
def stream_review():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename or not file.filename.endswith('.zip'):
        return jsonify({'error': 'Only .zip files are allowed'}), 400
    # Block double extensions like .exe.zip, .bat.zip
    base = file.filename.rsplit('.', 1)[0].lower()
    dangerous_exts = {'.exe', '.bat', '.cmd', '.com', '.msi', '.scr', '.pif', '.vbs', '.js', '.ps1'}
    if any(base.endswith(ext) for ext in dangerous_exts):
        return jsonify({'error': 'Files with dangerous extensions are not allowed'}), 400

    user_uuid = session.get('user_uuid', '')
    logger_skills.info(f"Stream review started", extra={'detail': f"user_uuid={user_uuid} filename={file.filename}"})

    zip_path, extract_dir, manifest, skill_md, py_contents, error_reason = load_skill(
        file, app.config['UPLOAD_FOLDER'], app.config['SKILLS_DIR']
    )
    skill_id = str(uuid.uuid4())
    all_py_code = "\n".join(py_contents) if py_contents else ""

    def generate():
        if not extract_dir:
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            reject_skill(skill_id, user_uuid)
            logger_skills.warning(f"Stream review failed (extraction)", extra={'detail': f"skill_id={skill_id} reason={error_reason}"})
            yield f"data: {json.dumps({'type': 'error', 'error': error_reason}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        description = manifest.get('description', '')
        user_question = request.form.get('user_question', description or 'Проанализируйте навык на безопасность и корректность.')

        yield f"data: {json.dumps({'type': 'status', 'text': 'AI-ревью...'}, ensure_ascii=False)}\n\n"

        # Проверка обязательных файлов перед AI-ревью
        if not skill_md:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Отсутствует обязательный файл skill.md'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            shutil.rmtree(extract_dir, ignore_errors=True)
            reject_skill(skill_id, user_uuid)
            logger_skills.warning(f"Skill validation failed", extra={'detail': f"skill_id={skill_id} reason=skill.md missing"})
            return

        review_stream = ai_review_stream(user_question, skill_md, all_py_code, description)
        approved = True
        rejection_reason = ""
        for chunk in review_stream:
            if isinstance(chunk, dict):
                if not chunk.get('approved', True):
                    approved = False
                    rejection_reason = chunk.get('reason', 'Отклонено AI-ревьюером')
                yield f"data: {json.dumps({'type': 'result', **chunk}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'chunk', 'text': str(chunk)}, ensure_ascii=False)}\n\n"

        if approved:
            # Register after successful review
            skill_dir = os.path.join(app.config['SKILLS_DIR'], skill_id)
            shutil.move(extract_dir, skill_dir)
            register_skill(skill_id, manifest, skill_md, all_py_code, user_uuid)
            logger_skills.info(f"Stream review passed", extra={'detail': f"skill_id={skill_id} name={manifest.get('name', 'Unknown')}"})
        else:
            shutil.rmtree(extract_dir, ignore_errors=True)
            reject_skill(skill_id, user_uuid)
            logger_skills.warning(f"Stream review rejected", extra={'detail': f"skill_id={skill_id} reason={rejection_reason}"})
        os.remove(zip_path)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
