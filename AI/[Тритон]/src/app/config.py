import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    flag: str
    database_path: Path


def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "TritonWebMid: эскалация через shared memory"),
        flag=os.getenv("FLAG", "FLAG_NOT_CONFIGURED"),
        database_path=Path(
            os.getenv("TRITON_DB_PATH", "data/triton_challenge.sqlite3")
        ),
    )
