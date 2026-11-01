"""Server settings, read once from environment variables (see .env.example and deploy/vps/.env.example)."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass
class Config:
    data_dir: Path
    org_name: str = "My organisation"
    session_idle_min: int = 30  # minutes of inactivity before an admin is signed out
    session_max_hours: int = 12  # the longest one sign-in lasts
    cookie_secure: bool = True  # the sign-in cookie is only sent over HTTPS
    tls: bool = True  # False = plain HTTP, only behind a proxy that does HTTPS (deploy/vps)
    behind_proxy: bool = False  # trust the client address and scheme that the proxy passes on
    admin_allow: list[Network] = field(default_factory=list)  # who may open the admin pages; empty = anyone

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ssas.sqlite3"

    @property
    def cert_file(self) -> Path:
        return self.data_dir / "certs" / "server.crt"

    @property
    def key_file(self) -> Path:
        return self.data_dir / "certs" / "server.key"


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value not in ("0", "false", "no", "off")


def parse_networks(text: str) -> list[Network]:
    """'192.168.1.0/24, 10.0.0.5' -> networks. Raises ValueError on a typo, so a bad list never means 'anyone'."""
    return [ipaddress.ip_network(part.strip(), strict=False) for part in text.split(",") if part.strip()]


def load() -> Config:
    data = Path(os.environ.get("SSAS_DATA_DIR", "./data"))
    data.mkdir(parents=True, exist_ok=True)
    return Config(
        data_dir=data,
        # SSAS_SCHOOL_NAME is the 0.1 name of the setting, still read so old .env files keep working.
        org_name=os.environ.get("SSAS_ORG_NAME") or os.environ.get("SSAS_SCHOOL_NAME") or "My organisation",
        session_idle_min=int(os.environ.get("SSAS_SESSION_IDLE_MIN", "30")),
        session_max_hours=int(os.environ.get("SSAS_SESSION_MAX_HOURS", "12")),
        cookie_secure=_flag("SSAS_COOKIE_SECURE", True),
        tls=_flag("SSAS_TLS", True),
        behind_proxy=_flag("SSAS_BEHIND_PROXY", False),
        admin_allow=parse_networks(os.environ.get("SSAS_ADMIN_ALLOW", "")),
    )
