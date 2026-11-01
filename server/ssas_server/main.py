"""Builds the web app: the screens' API (api.py), the admin pages (pages.py) and the protections (security.py).

Run it with `python -m ssas_server` (see __main__.py), or in tests with create_app(Config(...)).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, api, pages
from .config import Config, load
from .db import Database
from .security import Guard, RateLimit

HERE = Path(__file__).parent
STATUS_LABELS = {
    "present": "Present",
    "absent": "Absent",
    "needs_review": "Needs review",
    "no_data": "No data",
    "late": "Late",
}
LOGIN_ATTEMPTS_PER_ADDRESS = 10  # within LOGIN_WINDOW_S, whatever the account
LOGIN_WINDOW_S = 600


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load()
    app = FastAPI(title="SSAS server", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    app.state.db = Database(cfg.db_path)
    app.state.login_limit = RateLimit(LOGIN_ATTEMPTS_PER_ADDRESS, LOGIN_WINDOW_S)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(org=cfg.org_name, version=__version__, labels=STATUS_LABELS)
    app.state.templates = templates

    app.add_middleware(Guard, cfg=cfg)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(api.router)
    app.include_router(pages.router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code == 303:  # need_login() sends the browser to the sign-in page
            return RedirectResponse(exc.headers["Location"], status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "bad request"}, status_code=400)

    return app
