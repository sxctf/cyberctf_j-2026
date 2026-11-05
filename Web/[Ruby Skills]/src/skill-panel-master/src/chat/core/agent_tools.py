from langchain.tools import tool
import os, re
import sqlite3
import time
import subprocess
import tempfile
import bcrypt
import uuid
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logging_config import logger_code

_CHAT_DIR = os.path.dirname(os.path.dirname(__file__))
SKILLS_DIR = os.path.join(_CHAT_DIR, "tmp", "skills")
SKILLS_DB = os.path.join(_CHAT_DIR, "data", "skills.db")

_current_user_uuid: str = ""


def set_current_user_uuid(user_uuid: str):
    """Set the current user UUID for tool context."""
    global _current_user_uuid
    _current_user_uuid = user_uuid


def get_db():
    """Get SQLite connection, create tables if needed."""
    os.makedirs(os.path.dirname(SKILLS_DB), exist_ok=True)
    conn = sqlite3.connect(SKILLS_DB)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_registry (
            skill_id TEXT PRIMARY KEY,
            user_uuid TEXT NOT NULL,
            status TEXT NOT NULL,
            registered_at REAL,
            FOREIGN KEY (user_uuid) REFERENCES users(user_uuid) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_details (
            skill_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            version TEXT,
            main_file TEXT,
            files TEXT,
            skill_md_preview TEXT,
            skill_py_preview TEXT,
            FOREIGN KEY (skill_id) REFERENCES skill_registry(skill_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_uuid TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at REAL
        )
    """)
    conn.commit()
    return conn


@tool("square_root", description="Calculate the square root of a number")
def sqrt(x: float) -> float:
    return x ** 0.5


@tool("chinese-translator", description="Translate English or Russian text to Chinese")
def ch_translator(text: str) -> str:
    return text + "\n"


@tool("esperanto-translator", description="Translate English or Russian text to Esperanto")
def eo_translate(text: str) -> str:
    return text + "\n"


@tool("get_skill_list", description="""Get the list of all available custom skills.
ONLY call this tool if the user's request explicitly requires a specialized calculation, conversion, 
or action that you cannot perform using your core knowledge. 
DO NOT call this tool for general conversation, greetings, jokes, or writing standard text/code.""")
def get_skill_list() -> str:
    """Return list of available skills with their names only."""
    try:
        conn = get_db()
        cur = conn.execute(
            "SELECT d.name FROM skill_registry r "
            "JOIN skill_details d ON r.skill_id = d.skill_id "
            "WHERE r.status = 'success' AND r.user_uuid = ?",
            (_current_user_uuid,)
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return "Нет загруженных навыков."

        return "Вот мои загруженные skills:\n" + "\n".join(f"- {name}" for (name,) in rows) + "\n"
    except Exception as e:
        return f"Ошибка получения списка: {e}"


@tool("search_skill", description="""Search for a skill by description or preview content.
Use this when the user's request matches an available skill's purpose to find the right skill code and documentation.
Parameters:
  query: keyword or phrase to search for in skill names, descriptions, and code previews.
Returns: matching skills with their real UUID, name, description, documentation preview, and the core Python code.""")
def search_skill(query: str) -> str:
    """Search skills in DB by query and return matching skills directly from DB."""
    try:
        conn = get_db()
        cur = conn.execute("""
            SELECT r.skill_id, d.name, d.description, d.version, d.skill_md_preview, d.skill_py_preview
            FROM skill_registry r
            JOIN skill_details d ON r.skill_id = d.skill_id
            WHERE r.status = 'success' AND r.user_uuid = ?
              AND (
                LOWER(d.name) LIKE ? OR
                LOWER(d.description) LIKE ? OR
                LOWER(d.skill_md_preview) LIKE ? OR
                LOWER(d.skill_py_preview) LIKE ?
              )
            LIMIT 5
        """, (
            _current_user_uuid,
            f"%{query.lower()}%",
            f"%{query.lower()}%",
            f"%{query.lower()}%",
            f"%{query.lower()}%",
        ))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return f"Нет навыков, подходящих под запрос: '{query}'"

        results = []
        for skill_id, name, description, version, md_content, py_code in rows:
            if not py_code:
                py_code = "(нет .py файлов)"

            results.append(f"""=== Навык: {name} ===
            ID для вызова (REAL_UUID): {skill_id}
            Описание: {description}
            Версия: {version}
            
            Документация (SKILL.md):
            {md_content if md_content else 'N/A'}

            Доступный исходный код Python для анализа:
            {py_code}""")  

        return "\n".join(results)
    except Exception as e:
        return f"Ошибка поиска навыка: {e}"


@tool("get_skill_content", description="""Получает полное содержимое конкретного скилла по его UUID.
Используй когда пользователь просит рассказать про конкретный навык или нужно увидеть его документацию и код.
Параметры:
  skill_id: точный UUID скилла из базы данных.
Returns: полное имя, описание, документация SKILL.md и весь Python-код скилла.""")
def get_skill_content(skill_id: str) -> str:
    """Return full content of a skill by its UUID."""
    try:
        conn = get_db()
        cur = conn.execute(
            "SELECT d.name, d.description, d.version, d.skill_md_preview, d.skill_py_preview "
            "FROM skill_registry r JOIN skill_details d ON r.skill_id = d.skill_id "
            "WHERE r.skill_id = ? AND r.status = 'success' AND r.user_uuid = ?",
            (skill_id, _current_user_uuid)
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return f"Скилл с ID '{skill_id}' не найден или недоступен."

        name, description, version, md_content, py_code = row

        result = f"=== Навык: {name} ===\n"
        result += f"ID: {skill_id}\n"
        result += f"Описание: {description}\n"
        result += f"Версия: {version}\n\n"
        result += f"--- Документация (SKILL.md) ---\n{md_content if md_content else 'N/A'}\n\n"
        result += f"--- Исходный код (Python) ---\n{py_code if py_code else '(нет .py файлов)'}"
        return result
    except Exception as e:
        return f"Ошибка получения содержимого: {e}"

@tool("execute_code_in_skill", description="""Выполняет вызов функции внутри контекста конкретного скилла.
Параметры:
  skill_id: точный UUID скилла из базы данных.
  expression: Python-код для вызова функции. Если передаешь дробные числа или сложные параметры, 
              ОБЯЗАТЕЛЬНО сначала объяви их как отдельные переменные на новых строках, 
              а затем передай в print(). Это предотвратит синтаксические ошибки генерации.
""")
def execute_code_in_skill(skill_id: str, expression: str) -> str:
    logger_code.info(f"Code execution requested", extra={'detail': f"skill_id={skill_id!r} expression={expression!r}"})
    """Запускает выражение внутри папки конкретного скилла, автоматически импортируя его main_file."""
    try:
        conn = get_db()
        # Проверка владения скиллом
        cur = conn.execute(
            "SELECT user_uuid, main_file FROM skill_details d "
            "JOIN skill_registry r ON r.skill_id = d.skill_id "
            "WHERE r.skill_id = ? AND r.status = 'success'",
            (skill_id,)
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return f"Ошибка: Скилл с ID '{skill_id}' не найден или недоступен."

        user_uuid, main_file = row
        if user_uuid != _current_user_uuid:
            return f"Ошибка: У вас нет доступа к этому скиллу."
        
        skill_folder_path = os.path.join(SKILLS_DIR, skill_id)

        if not os.path.exists(skill_folder_path):
            return f"Ошибка: Папка скилла на диске не найдена по пути {skill_folder_path}"
        
        
        main_file = row[1] 
        if not main_file or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*\.py", main_file):
            return "Ошибка: Некорректное имя main_file"

        module_name = os.path.splitext(main_file)[0]  

        main_file_path = os.path.join(skill_folder_path, main_file)
        if not os.path.isfile(main_file_path):
            return "Ошибка: main_file не найден в папке скилла"
       
        clean_expression = expression.replace("```python", "").replace("```", "").strip()
        clean_expression = clean_expression.replace(r"\u0027", "'").replace(r"\u0022", '"')
        clean_expression = clean_expression.rstrip('", \t\n\r')
        clean_expression = clean_expression.replace('\\"', '"').replace("\\'", "'")
        clean_expression = clean_expression.replace('\\', '') 


        script_lines = [
            f"from {module_name} import *",
            "",
            "# Если функция импортировалась как инструмент LangChain, чиним её",
            "for name in list(globals().keys()):",
            "    obj = globals()[name]",
            "    if hasattr(obj, 'func'):",
            "        globals()[name] = obj.func",
            "",
            clean_expression
        ]
        

        full_script = "\n".join(script_lines) + "\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8', dir=skill_folder_path) as f:
            f.write(full_script)
            f.flush()
            tmp_path = f.name

        try:
            safe_env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ["KEY", "SECRET", "TOKEN", "PASSWORD"])}
            safe_env["PYTHONIOENCODING"] = "utf-8"

            # Запуск строго в контексте папки скилла
            result = subprocess.run(
                ["python3", os.path.basename(tmp_path)],
                capture_output=True,
                text=True,
                timeout=30,
                env=safe_env,
                cwd=skill_folder_path 
            )

            output = "Результат:\n"
            if result.stdout:
                output += result.stdout.strip() + "\n"
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr.strip()

            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]\n"

            logger_code.info(f"Code execution completed", extra={'detail': f"skill_id={skill_id} returncode={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}"})
            return output if output else "(выполнено успешно)"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        return f"Ошибка среды выполнения: {e}\n"


# ── Registration helper ──

def register_skill(skill_id: str, manifest: dict, skill_md: str, skill_py: str = "", user_uuid: str = ""):
    """Register a successfully uploaded skill in the database, saving FULL code and docs."""
    main_file = manifest.get("main_file", "")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*\.py", main_file or ""):
        raise ValueError("Некорректное имя main_file")
    
    files_list = ["manifest.json", "skill.md"]
    if skill_py:
        files_list.append(os.path.basename(main_file) if main_file else "skill.py")

    conn = get_db()
    now = time.time()

    # 1. Помечаем в реестре, что навык успешно добавлен
    conn.execute(
        """INSERT OR REPLACE INTO skill_registry (skill_id, user_uuid, status, registered_at)
           VALUES (?, ?, 'success', ?)""",
        (skill_id, user_uuid, now)
    )

    # 2. Сохраняем в детали навыка ПОЛНЫЙ текст (убираем обрезку [:500])
    # Теперь skill_md_preview и skill_py_preview хранят весь контент для агента!
    conn.execute(
        """INSERT OR REPLACE INTO skill_details
           (skill_id, name, description, version, main_file, files, skill_md_preview, skill_py_preview)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            skill_id,
            manifest.get("name", "Unknown Skill"),
            manifest.get("description", ""),
            manifest.get("version", "1.0"),
            main_file,
            ", ".join(files_list),
            skill_md,  # Сохраняем весь SKILL.md целиком
            skill_py,  # Сохраняем весь Python-код целиком
        )
    )
    conn.commit()
    conn.close()


def reject_skill(skill_id: str, user_uuid: str = ""):
    """Mark a skill as rejected in the database."""
    conn = get_db()
    now = time.time()
    conn.execute(
        """INSERT OR REPLACE INTO skill_registry (skill_id, user_uuid, status, registered_at)
           VALUES (?, ?, 'rejected', ?)""",
        (skill_id, user_uuid, now)
    )
    conn.commit()
    conn.close()


# ── Authentication helpers ──

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def register_user(username: str, password: str) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (success: bool, message: str).
    Uses parameterized queries — safe from SQLi.
    Generates a UUID4 for the user.
    """
    # Basic validation
    if not username or not password:
        return False, "Заполните все поля"
    if len(username) < 3 or len(username) > 80:
        return False, "Имя пользователя: от 3 до 80 символов"
    if not username.isalnum():
        return False, "Имя пользователя: только буквы и цифры"
    if len(password) < 6:
        return False, "Пароль: минимум 6 символов"

    password_hash = hash_password(password)
    user_uuid = str(uuid.uuid4())
    now = time.time()

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (user_uuid, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_uuid, username, password_hash, now)
        )
        conn.commit()
        conn.close()
        return True, user_uuid
    except sqlite3.IntegrityError:
        return False, "Пользователь с таким именем уже существует"


def authenticate_user(username: str, password: str) -> tuple[bool, str | None]:
    """
    Authenticate a user by username and password.
    Returns (success: bool, user_uuid: str | None).
    Uses parameterized query — safe from SQLi.
    """
    conn = get_db()
    cur = conn.execute(
        "SELECT user_uuid, password_hash FROM users WHERE username = ?",
        (username,)
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return False, None

    user_uuid, password_hash = row
    if check_password(password, password_hash):
        return True, user_uuid
    return False, None
