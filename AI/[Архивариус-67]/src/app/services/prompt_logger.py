import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.environ.get("PEER_REVIEW_PROMPT_LOG", "/tmp/prompts.log")

# Create the parent directory if missing (Windows has no /tmp by default).
_parent = os.path.dirname(os.path.abspath(LOG_PATH))
if _parent:
    os.makedirs(_parent, exist_ok=True)

_logger = logging.getLogger("prompt_logger")
_logger.setLevel(logging.DEBUG)

_handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_logger.addHandler(_handler)


def log_prompt(
    request_id: str,
    stage: str,
    system_prompt: str,
    user_message: str,
    response: str | None = None,
) -> None:
    header = f"[{request_id}] [{stage}]"
    _logger.info("%s SYSTEM>>> %s", header, system_prompt.replace("\n", "\\n"))
    _logger.info("%s USER>>> %s", header, user_message.replace("\n", "\\n"))
    if response is not None:
        _logger.info("%s RESPONSE<<< %s", header, response.replace("\n", "\\n"))
