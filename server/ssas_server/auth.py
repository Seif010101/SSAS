"""Admin accounts: password (Argon2id) + 6-digit TOTP, lockout, sessions and CSRF tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from .db import Database, now

_ph = PasswordHasher()
MAX_FAILED = 5
LOCK_MINUTES = 15
ROLES = ("developer", "supervisor")


@dataclass
class Admin:
    id: int
    email: str
    name: str
    role: str

    @property
    def can_edit(self) -> bool:
        return self.role == "developer"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def create_admin(db: Database, email: str, name: str, role: str, password: str) -> str:
    """Create an admin; returns the TOTP secret to add to the authenticator app."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if len(password) < 10:
        raise ValueError("The password must have at least 10 characters.")
    secret = pyotp.random_base32()
    db.exec(
        "INSERT INTO admins (email, name, role, pw_hash, totp_secret, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (email.strip().lower(), name.strip(), role, _ph.hash(password), secret, now()),
    )
    db.audit("cli", "admin.create", {"email": email, "role": role})
    return secret


def provisioning_uri(secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def reset_totp(db: Database, email: str) -> str:
    secret = pyotp.random_base32()
    if db.exec("UPDATE admins SET totp_secret = ?, last_totp_step = 0 WHERE email = ?", (secret, email.lower())) == 0:
        raise ValueError("No such admin")
    db.audit("cli", "admin.reset_totp", {"email": email})
    return secret


def set_password(db: Database, email: str, password: str) -> None:
    if len(password) < 10:
        raise ValueError("The password must have at least 10 characters.")
    if db.exec("UPDATE admins SET pw_hash = ?, failed = 0, locked_until = NULL WHERE email = ?",
               (_ph.hash(password), email.lower())) == 0:
        raise ValueError("No such admin")
    db.audit("cli", "admin.set_password", {"email": email})


class LoginError(Exception):
    pass


def login(db: Database, email: str, password: str, code: str, at: float | None = None) -> Admin:
    """Check password and TOTP; raises LoginError with a message safe to show."""
    at = time.time() if at is None else at
    row = db.one("SELECT * FROM admins WHERE email = ?", (email.strip().lower(),))
    generic = "Wrong email, password or code."
    if row is None:
        _ph.hash("dummy-password-to-even-out-timing")
        raise LoginError(generic)
    if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > datetime.now(timezone.utc):
        raise LoginError("Too many attempts. Try again in 15 minutes.")
    ok = True
    try:
        _ph.verify(row["pw_hash"], password)
    except (VerifyMismatchError, VerificationError):
        ok = False
    step = _totp_step(row["totp_secret"], code.strip().replace(" ", ""), at)
    if step is None or step <= row["last_totp_step"]:
        ok = False  # wrong code, or a code that was already used (replay)
    if not ok:
        failed = row["failed"] + 1
        locked = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).isoformat() if failed >= MAX_FAILED else None
        db.exec("UPDATE admins SET failed = ?, locked_until = ? WHERE id = ?", (0 if locked else failed, locked, row["id"]))
        db.audit(row["email"], "login.failed", {"locked": bool(locked)})
        raise LoginError(generic)
    db.exec("UPDATE admins SET failed = 0, locked_until = NULL, last_totp_step = ? WHERE id = ?", (step, row["id"]))
    if _ph.check_needs_rehash(row["pw_hash"]):
        db.exec("UPDATE admins SET pw_hash = ? WHERE id = ?", (_ph.hash(password), row["id"]))
    db.audit(row["email"], "login.ok", {})
    return Admin(row["id"], row["email"], row["name"], row["role"])


def _totp_step(secret: str, code: str, at: float) -> int | None:
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    for offset in (0, -1, 1):  # accept one 30-second step of clock difference
        t = at + offset * 30
        if hmac.compare_digest(totp.at(t), code):
            return int(t // 30)
    return None


# ----- sessions -----
def new_session(db: Database, admin: Admin) -> str:
    token = secrets.token_urlsafe(32)
    db.exec("INSERT INTO sessions (token_hash, admin_id, created_at, last_seen) VALUES (?, ?, ?, ?)",
            (_sha(token), admin.id, now(), now()))
    return token


def session_admin(db: Database, token: str | None, idle_min: int, max_hours: int) -> Admin | None:
    if not token:
        return None
    row = db.one(
        "SELECT s.created_at, s.last_seen, a.id, a.email, a.name, a.role FROM sessions s "
        "JOIN admins a ON a.id = s.admin_id WHERE s.token_hash = ?", (_sha(token),))
    if row is None:
        return None
    t = datetime.now(timezone.utc)
    if (t - datetime.fromisoformat(row["last_seen"]) > timedelta(minutes=idle_min)
            or t - datetime.fromisoformat(row["created_at"]) > timedelta(hours=max_hours)):
        end_session(db, token)
        return None
    db.exec("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (now(), _sha(token)))
    return Admin(row["id"], row["email"], row["name"], row["role"])


def end_session(db: Database, token: str | None) -> None:
    if token:
        db.exec("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))


def csrf_token(session_token: str) -> str:
    return hashlib.sha256(("csrf:" + session_token).encode()).hexdigest()[:32]


def check_csrf(session_token: str | None, given: str | None) -> bool:
    return bool(session_token and given and hmac.compare_digest(csrf_token(session_token), given))
