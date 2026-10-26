"""Run the server with HTTPS: python -m ssas_server"""

import os

import uvicorn

from .cli import ensure_cert
from .config import load
from .main import create_app


def run() -> None:
    cfg = load()
    ensure_cert(cfg)
    uvicorn.run(create_app(cfg), host=os.environ.get("SSAS_HOST", "0.0.0.0"), port=int(os.environ.get("SSAS_PORT", "8443")),
                ssl_certfile=str(cfg.cert_file), ssl_keyfile=str(cfg.key_file), proxy_headers=False, workers=1)


run()
