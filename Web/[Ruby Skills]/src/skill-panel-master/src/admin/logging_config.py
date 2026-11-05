import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

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


def _setup_logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    """Создаёт логгер с хэндлерами: файл + stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = JSONFormatter()

    # File
    filepath = os.path.join(LOG_DIR, filename)
    fh = logging.FileHandler(filepath, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Stdout (для docker logs)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger

logger_admin = _setup_logger('skill-panel.admin', 'admin.log')
