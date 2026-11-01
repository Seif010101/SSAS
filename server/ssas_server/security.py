"""Protections in front of every request (see docs/security.md):

- security headers on every answer (no framing, no scripts, no sniffing, no referrer);
- a size limit on what a request may send (413 when bigger);
- the optional list of addresses allowed to open the admin pages (SSAS_ADMIN_ALLOW);
- a limit on sign-in attempts per address (429 when exceeded), on top of the per-account lock;
- CSV cells that cannot run as Excel formulas.
"""

from __future__ import annotations

import ipaddress
import threading
import time
import unicodedata
from collections import deque

from fastapi import HTTPException

from .config import Config

HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
}
HSTS = "max-age=31536000"

UPLOAD_PATHS = {"/boards/import"}
UPLOAD_LIMIT = 4 * 1024 * 1024  # boards.json
REQUEST_LIMIT = 256 * 1024  # everything else (a result for a big group is a few kilobytes)


class Guard:
    """ASGI middleware that applies the size limit, the admin address list and the security headers."""

    def __init__(self, app, cfg: Config):
        self.app = app
        self.cfg = cfg

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path: str = scope["path"]
        secure = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = dict(HEADERS)
                if secure:
                    extra["strict-transport-security"] = HSTS
                if not path.startswith("/static/"):
                    extra["cache-control"] = "no-store"  # pages hold people's names
                headers += [(k.encode(), v.encode()) for k, v in extra.items() if k.encode() not in present]
                message = {**message, "headers": headers}
            await send(message)

        if not path.startswith("/api/") and not self.admin_allowed(scope):
            return await plain(send_with_headers, 403, "The admin pages cannot be opened from this address.")

        limit = UPLOAD_LIMIT if path in UPLOAD_PATHS else REQUEST_LIMIT
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            if not length.isdigit():
                return await plain(send_with_headers, 400, "Bad Content-Length.")
            if int(length) > limit:
                return await plain(send_with_headers, 413, "Request too large.")
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:  # a body sent without Content-Length
                    raise HTTPException(413, "Request too large.")
            return message

        await self.app(scope, limited_receive, send_with_headers)

    def admin_allowed(self, scope) -> bool:
        if not self.cfg.admin_allow:
            return True
        client = scope.get("client")
        try:
            ip = ipaddress.ip_address(client[0]) if client else None
        except ValueError:
            return False
        return ip is not None and any(ip in net for net in self.cfg.admin_allow)


async def plain(send, status: int, text: str) -> None:
    body = text.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RateLimit:
    """At most `limit` events per `window` seconds for each key (for example sign-in attempts per address)."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float:
        """Count one event. Returns 0 when it is allowed, otherwise the seconds to wait."""
        t = time.monotonic()
        with self._lock:
            q = self._events.setdefault(key, deque())
            while q and t - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return self.window - (t - q[0])
            q.append(t)
            if len(self._events) > 10_000:  # forget addresses that went quiet
                self._events = {k: v for k, v in self._events.items() if v and t - v[-1] <= self.window}
            return 0.0


def csv_cell(value) -> str:
    """Text that Excel shows as text: a leading = + - @ (or tab / return) would make it a formula."""
    s = "" if value is None else str(value)
    first = unicodedata.normalize("NFKC", s[:1])  # also catches full-width ＝ ＋ － ＠
    return "'" + s if first in ("=", "+", "-", "@", "\t", "\r") else s
