from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    flag: str
    host: str
    port: int
    enable_admin_routes: bool
    agent_name: str
    console_title: str
    experiment_name: str
    gigachat_credentials: str
    gigachat_scope: str
    gigachat_model: str
    gigachat_timeout: float
    gigachat_verify_ssl_certs: bool
    llm_backend: str


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        flag=os.environ.get("PEER_REVIEW_FLAG")
        or os.environ.get("FLAG")
        or "RRC{demo_flag_replace_me}",
        host=os.environ.get("PEER_REVIEW_HOST", "127.0.0.1"),
        port=int(os.environ.get("PEER_REVIEW_PORT", "8000")),
        enable_admin_routes=_env_bool("ARCHIVE_ENABLE_ADMIN_ROUTES", False),
        agent_name="Архивариус-67",
        console_title="НИИ РАБО-ИИ · Архивный стенд",
        experiment_name="Архив-7 / Каталог научных отчётов",
        gigachat_credentials=os.environ.get("GIGACHAT_CREDENTIALS", ""),
        gigachat_scope=(
            "GIGACHAT_API_CORP"
            if _env_bool("GIGACHAT_CORP_SCOPE", False)
            else "GIGACHAT_API_PERS"
        ),
        gigachat_model=os.environ.get("GIGACHAT_MODEL", "GigaChat-2-Max"),
        gigachat_timeout=float(os.environ.get("GIGACHAT_TIMEOUT", "60")),
        gigachat_verify_ssl_certs=_env_bool("GIGACHAT_VERIFY_SSL_CERTS", False),
        llm_backend=os.environ.get("ARCHIVE_LLM_BACKEND", "gigachat").strip().lower(),
    )
