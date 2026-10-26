from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    data_dir: Path
    school_name: str
    session_idle_min: int = 30
    session_max_hours: int = 12
    cookie_secure: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ssas.sqlite3"

    @property
    def cert_file(self) -> Path:
        return self.data_dir / "certs" / "server.crt"

    @property
    def key_file(self) -> Path:
        return self.data_dir / "certs" / "server.key"


def load() -> Config:
    data = Path(os.environ.get("SSAS_DATA_DIR", "./data"))
    data.mkdir(parents=True, exist_ok=True)
    return Config(
        data_dir=data,
        school_name=os.environ.get("SSAS_SCHOOL_NAME", "School"),
        session_idle_min=int(os.environ.get("SSAS_SESSION_IDLE_MIN", "30")),
        session_max_hours=int(os.environ.get("SSAS_SESSION_MAX_HOURS", "12")),
        cookie_secure=os.environ.get("SSAS_COOKIE_SECURE", "true").lower() != "false",
    )
