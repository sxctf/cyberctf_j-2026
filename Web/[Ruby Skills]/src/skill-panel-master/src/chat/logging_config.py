import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# ── Форматировщик ──
class JSONFormatter(logging.Formatter):
    """Форматирует лог в читаемый текстовый вид с timestamp."""
    def format(self, record):
        ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        detail = getattr(record, 'detail', '')
        return (
            f"{ts} | {record.levelname:<7} | {record.name:<25} | "
            f"{record.getMessage()}"
            + (f" | {detail}" if detail else "")
        )


LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _setup_logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    """Создаёт логгер с хэндлерами: ротированный файл + stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = JSONFormatter()

    # Файл с ротацией по размеру (без бэкапов)
    filepath = os.path.join(LOG_DIR, filename)
    fh = RotatingFileHandler(filepath, maxBytes=LOG_MAX_BYTES, backupCount=20, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Stdout (для docker logs)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger


# ── Логгеры ──
logger_auth = _setup_logger('skill-panel.auth', 'auth.log')
logger_skills = _setup_logger('skill-panel.skills', 'skills.log')
logger_code = _setup_logger('skill-panel.code', 'code.log')
logger_chat = _setup_logger('skill-panel.chat', 'chat.log')
